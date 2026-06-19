# -*- coding: utf-8 -*-
"""
네이버 메일 → 노션 브리핑 자동 작성기
─────────────────────────────────────
하는 일:
  1) 네이버 메일 계정 2개에서 '직전 실행 이후' 새로 온 메일을 IMAP으로 읽어온다.
  2) 제목에 협업 키워드가 있으면 '협업 메일', 아니면 '일반 메일'로 분류한다.
  3) 노션 부모 페이지 아래에 새 하위 페이지를 만들어 정리한다.
  4) 이번 실행 시각을 기록해서 다음 번 중복을 막는다.

* AI 요약은 사용하지 않음. 보낸사람 / 제목 / 받은시간만 표시.
* 비밀값(이메일/앱비번/노션토큰/페이지ID)은 전부 환경변수로 받음.
"""

import os
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


# ════════════════════════════════════════════════════════════
#  1. 준비 — 비밀값 불러오기 & 설정값 정의
# ════════════════════════════════════════════════════════════

# .env 파일에 적힌 값을 환경변수처럼 불러온다.
# (GitHub Actions에서는 .env가 없고 Secrets가 환경변수로 들어오므로 자동으로 그쪽을 쓴다.)
load_dotenv()

# 한국 시간대 (UTC+9). 받은시간을 한국시간으로 표시하기 위해 사용.
KST = timezone(timedelta(hours=9))

# '협업 메일'로 분류할 키워드. 제목에 이 중 하나라도 들어있으면 협업 메일.
COLLAB_KEYWORDS = [
    "협업", "프로젝트", "공유", "미팅", "회의",
    "외주", "계약", "요청", "체험단", "파트너", "문의",
]

# 직전 실행 시각을 기억해 두는 메모지 파일 이름.
LAST_RUN_FILE = "last_run.txt"

# 만약 '직전 실행 기록'이 아예 없을 때(맨 처음 실행 등),
# 최근 몇 시간 안에 온 메일을 가져올지 정하는 기본값(시간).
DEFAULT_LOOKBACK_HOURS = 24


def get_naver_accounts():
    """환경변수에서 네이버 계정 정보들을 모아 리스트로 돌려준다.
    NAVER_EMAIL_1 / NAVER_APP_PASSWORD_1, _2, _3 ... 순서로 있는 만큼 읽는다.
    (계정이 2개든 3개든 자동으로 인식)"""
    accounts = []
    index = 1
    while True:
        email_addr = os.getenv(f"NAVER_EMAIL_{index}")
        app_pw = os.getenv(f"NAVER_APP_PASSWORD_{index}")
        # 둘 중 하나라도 비어있으면 더 이상 계정이 없는 것으로 보고 멈춘다.
        if not email_addr or not app_pw:
            break
        accounts.append({"email": email_addr.strip(), "password": app_pw.strip()})
        index += 1
    return accounts


def get_last_run_time():
    """직전 실행 시각을 읽어온다.
    기록이 없으면 '지금으로부터 DEFAULT_LOOKBACK_HOURS 시간 전'을 돌려준다."""
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
            # 저장된 글자(ISO 형식)를 다시 시간 값으로 바꾼다.
            return datetime.fromisoformat(saved)
        except Exception:
            pass  # 파일이 깨졌으면 아래 기본값으로 넘어간다.
    return datetime.now(KST) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)


def save_last_run_time(when):
    """이번 실행 시각을 메모지에 적어둔다 (다음 번 중복 방지용)."""
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(when.isoformat())


# ════════════════════════════════════════════════════════════
#  2. 네이버 메일 읽기 (IMAP)
# ════════════════════════════════════════════════════════════

def decode_mime_words(raw):
    """메일 제목/보낸사람은 암호처럼 인코딩돼 올 때가 많다.
    그걸 사람이 읽을 수 있는 한글/영문 글자로 풀어준다."""
    if raw is None:
        return ""
    parts = decode_header(raw)
    decoded = ""
    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                decoded += text.decode(charset or "utf-8", errors="replace")
            except (LookupError, TypeError):
                decoded += text.decode("utf-8", errors="replace")
        else:
            decoded += text
    return decoded.strip()


def fetch_new_mails(account, since_time):
    """계정 하나에 접속해서 since_time 이후에 온 메일들의
    (보낸사람 / 제목 / 받은시간)만 모아 돌려준다."""
    results = []
    try:
        # 네이버 IMAP 서버에 보안(SSL) 접속
        imap = imaplib.IMAP4_SSL("imap.naver.com", 993)
        imap.login(account["email"], account["password"])
        imap.select("INBOX")  # 받은편지함 선택

        # IMAP 검색은 '날짜' 단위까지만 거를 수 있어서,
        # since_time 의 '그 날짜'부터 일단 넓게 가져온 뒤,
        # 아래에서 정확한 '시각'으로 다시 한 번 거른다.
        date_str = since_time.astimezone(KST).strftime("%d-%b-%Y")
        status, data = imap.search(None, f'(SINCE "{date_str}")')
        if status != "OK":
            imap.logout()
            return results

        mail_ids = data[0].split()
        for mail_id in mail_ids:
            # 본문은 안 받고, 헤더(보낸사람/제목/날짜)만 빠르게 가져온다.
            status, msg_data = imap.fetch(
                mail_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_mime_words(msg.get("Subject"))
            sender = decode_mime_words(msg.get("From"))

            # 받은시간 헤더를 한국시간으로 변환
            received = None
            date_header = msg.get("Date")
            if date_header:
                try:
                    received = parsedate_to_datetime(date_header)
                    if received.tzinfo is None:
                        received = received.replace(tzinfo=KST)
                    received = received.astimezone(KST)
                except Exception:
                    received = None

            # since_time 이후에 온 메일만 채택 (정확한 시각 비교 = 중복 방지)
            if received is None or received <= since_time:
                continue

            results.append({
                "account": account["email"],
                "sender": sender,
                "subject": subject,
                "received": received,
            })

        imap.logout()
    except Exception as e:
        # 한 계정에서 문제가 생겨도 전체가 멈추지 않도록 메시지만 남기고 넘어간다.
        print(f"[경고] {account['email']} 메일을 읽는 중 문제 발생: {e}")
    return results


def is_collab(subject):
    """제목에 협업 키워드가 하나라도 들어있으면 True."""
    return any(keyword in subject for keyword in COLLAB_KEYWORDS)


# ════════════════════════════════════════════════════════════
#  3. 노션에 쓰기 (API)
# ════════════════════════════════════════════════════════════

NOTION_API = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"  # 노션 API 버전 (고정)


def notion_headers(token):
    """노션과 대화할 때 매번 붙이는 '신분증'(헤더)."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def text_block(content, emoji=""):
    """노션 페이지에 들어갈 '문단 한 줄'을 만든다."""
    prefix = f"{emoji} " if emoji else ""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": prefix + content}}]
        },
    }


def heading_block(content):
    """노션 페이지의 '소제목'(굵은 줄)을 만든다."""
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": content}}]
        },
    }


def divider_block():
    """노션 페이지의 '구분선'(가로줄)을 만든다."""
    return {"object": "block", "type": "divider", "divider": {}}


def build_mail_line(mail):
    """메일 한 통을 '보낸사람 · 제목 · 받은시간' 한 줄 글자로 만든다."""
    when = mail["received"].strftime("%m/%d %H:%M") if mail["received"] else "시간미상"
    return f"📨 {mail['sender']} | {mail['subject']} | {when}"


def create_briefing_page(token, parent_page_id, title, collab_mails, normal_mails):
    """노션 부모 페이지 아래에 새 하위 페이지를 만들어 메일을 정리한다."""
    children = []  # 페이지 안에 들어갈 내용(블록)들을 차곡차곡 담는다.

    # ── 협업 메일 (맨 위, 강조) ──
    children.append(heading_block(f"🔥 협업 메일 ({len(collab_mails)}건)"))
    if collab_mails:
        for mail in collab_mails:
            children.append(text_block(build_mail_line(mail), emoji="⭐"))
    else:
        children.append(text_block("협업 메일이 없습니다."))

    children.append(divider_block())

    # ── 일반 메일 (그 아래) ──
    children.append(heading_block(f"📥 일반 메일 ({len(normal_mails)}건)"))
    if normal_mails:
        for mail in normal_mails:
            children.append(text_block(build_mail_line(mail)))
    else:
        children.append(text_block("일반 메일이 없습니다."))

    # 노션에 보낼 데이터 한 묶음
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": children,
    }

    response = requests.post(NOTION_API, headers=notion_headers(token), json=payload)
    if response.status_code == 200:
        print(f"[성공] 노션 페이지 생성: {title}")
    else:
        print(f"[오류] 노션 페이지 생성 실패 ({response.status_code}): {response.text}")
    return response


# ════════════════════════════════════════════════════════════
#  4. 전체 실행 흐름
# ════════════════════════════════════════════════════════════

def make_title(now):
    """페이지 제목 만들기: '메일 브리핑 - 2026-06-19 오전'."""
    part = "오전" if now.hour < 12 else "오후"
    return f"메일 브리핑 - {now.strftime('%Y-%m-%d')} {part}"


def main():
    # (1) 비밀값 점검
    token = os.getenv("NOTION_TOKEN")
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    accounts = get_naver_accounts()

    if not token or not parent_page_id:
        print("[중단] NOTION_TOKEN 또는 NOTION_PARENT_PAGE_ID 환경변수가 없습니다.")
        return
    if not accounts:
        print("[중단] 네이버 계정 정보(NAVER_EMAIL_1 등) 환경변수가 없습니다.")
        return

    # (2) 직전 실행 시각 확인 → 그 이후 메일만 가져온다
    since_time = get_last_run_time()
    run_time = datetime.now(KST)
    print(f"[정보] {since_time.strftime('%Y-%m-%d %H:%M')} 이후 도착한 메일을 찾습니다.")

    # (3) 계정마다 메일 수집
    all_mails = []
    for account in accounts:
        mails = fetch_new_mails(account, since_time)
        print(f"[정보] {account['email']} : 새 메일 {len(mails)}건")
        all_mails.extend(mails)

    # (4) 받은시간 순으로 정렬 (최신이 위로)
    all_mails.sort(key=lambda m: m["received"] or run_time, reverse=True)

    # (5) 협업 / 일반 분류
    collab_mails = [m for m in all_mails if is_collab(m["subject"])]
    normal_mails = [m for m in all_mails if not is_collab(m["subject"])]

    # (6) 노션에 브리핑 페이지 작성
    title = make_title(run_time)
    create_briefing_page(token, parent_page_id, title, collab_mails, normal_mails)

    # (7) 이번 실행 시각 저장 (다음 번 중복 방지)
    save_last_run_time(run_time)
    print("[완료] 브리핑 작성을 마쳤습니다.")


if __name__ == "__main__":
    main()
