# 📬 네이버 메일 → 노션 브리핑 자동 작성기

네이버 메일 계정 2개의 새 메일을 읽어, 하루 3번(한국시간 08:00 / 13:00 / 19:00)
노션 페이지에 자동으로 정리해 주는 프로그램입니다.

- **협업 메일**(제목에 키워드 포함)은 맨 위에 강조 표시
- **일반 메일**은 그 아래에 `보낸사람 · 제목 · 받은시간`으로 목록 표시
- AI 요약 없음 / 모든 비밀값은 환경변수로 처리

협업 키워드: `협업, 프로젝트, 공유, 미팅, 회의, 외주, 계약, 요청, 체험단, 파트너, 문의`

---

## 1. 준비물 설정

### (A) 네이버 메일 — IMAP 켜기 + 앱 비밀번호 (계정 2개 모두)

1. **IMAP 켜기**: 네이버 메일 → 우측 상단 톱니(환경설정) → **POP3/IMAP 설정**
   → "IMAP/SMTP 사용" **사용함** 으로 변경 후 저장.
2. **앱 비밀번호 만들기**: 네이버 → 내정보(프로필) → 보안설정 →
   **애플리케이션 비밀번호 관리** → 새 비밀번호 생성(메일용).
   → 생성된 16자리 비밀번호를 복사해 둡니다. (로그인 비번이 아니라 이 값을 씁니다!)

### (B) 노션 — 인테그레이션 토큰 + 페이지 연결

1. https://www.notion.so/my-integrations 접속 → **New integration** 생성
   → 이름 입력 후 저장 → **Internal Integration Token**(secret_... 또는 ntn_...) 복사.
2. 브리핑을 쌓아둘 **노션 페이지**를 하나 만든다 (예: "메일 브리핑함").
3. 그 페이지 우측 상단 `•••` → **연결(Connections)** → 방금 만든 인테그레이션을 추가.
   (이걸 안 하면 프로그램이 페이지에 글을 못 씁니다!)
4. **페이지 ID 찾기**: 그 페이지를 브라우저에서 열면 주소(URL)가
   `https://www.notion.so/제목-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` 형태입니다.
   끝부분의 32자리 영문+숫자가 **페이지 ID** 입니다.

---

## 2. 내 컴퓨터에서 테스트하기 (로컬)

```powershell
# (1) .env.example 을 복사해 .env 만들기
Copy-Item .env.example .env

# (2) .env 파일을 열어 진짜 값(이메일/앱비번/노션토큰/페이지ID) 채우기

# (3) 필요한 라이브러리 설치
pip install -r requirements.txt

# (4) 실행
python main.py
```

성공하면 노션에 `메일 브리핑 - YYYY-MM-DD 오전/오후` 페이지가 새로 생깁니다.

---

## 3. GitHub Actions로 자동 실행하기

### (A) GitHub Secrets에 등록할 값 (총 6개)

저장소(repository) → **Settings → Secrets and variables → Actions**
→ **New repository secret** 버튼으로 아래 6개를 하나씩 등록합니다.
(이름은 아래와 똑같이 적어야 합니다. 값은 본인 것)

| Secret 이름 | 넣을 값 |
|---|---|
| `NAVER_EMAIL_1` | 첫 번째 네이버 이메일 (예: me1@naver.com) |
| `NAVER_APP_PASSWORD_1` | 첫 번째 계정의 앱 비밀번호 |
| `NAVER_EMAIL_2` | 두 번째 네이버 이메일 |
| `NAVER_APP_PASSWORD_2` | 두 번째 계정의 앱 비밀번호 |
| `NOTION_TOKEN` | 노션 인테그레이션 토큰 |
| `NOTION_PARENT_PAGE_ID` | 브리핑을 쌓아둘 노션 페이지 ID |

### (B) 실행 시각

`.github/workflows/briefing.yml` 에 한국시간 08:00 / 13:00 / 19:00로 설정돼 있습니다.
바꾸고 싶으면 그 파일의 `cron` 값을 수정하세요 (UTC = 한국시간 − 9시간).

### (C) 수동 테스트

저장소 → **Actions** 탭 → "메일 브리핑 자동 작성" → **Run workflow** 버튼으로
즉시 한 번 실행해 볼 수 있습니다.

---

## 4. 보안 메모

- 비밀값은 코드에 직접 쓰지 않고 전부 환경변수(.env / GitHub Secrets)로 처리합니다.
- `.env` 와 `last_run.txt` 는 `.gitignore` 에 등록되어 깃허브에 올라가지 않습니다.
- 혹시 토큰/비밀번호가 노출됐다면 즉시 노션·네이버에서 재발급하세요.
