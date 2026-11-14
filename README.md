# 주제 교체형 리포트 서비스

정해 둔 소스에서 새 소식과 논문을 자동으로 모아 **AI가 한국어로 요약**해 보내 주는 프로그램이에요.
보내는 곳은 **이메일 · 웹페이지 · 카카오톡(나에게 보내기)** 세 가지예요.

지금 들어 있는 주제는 **AI 동향 리포트**예요.

- Claude, Gemini, ChatGPT, Meta의 공식 업데이트
- 프롬프트·하네스·에이전트 관련 주목할 논문

**핵심 아이디어**: 코드는 그대로 두고 `topics/` 폴더에 설정 파일 하나만 새로 쓰면, 다른 주제(반도체, 부동산 정책 등)의 리포트 서비스가 돼요.

> **지금 설정**: 매주 월요일 06:30, 지난 7일의 **기술** 소식만 골라 **초보자용**으로 풀어서 **카카오톡으로만** 보내요.
> 쉬운 설명은 Claude 데스크톱 앱의 **예약 작업**이 구독으로 직접 써요. Claude API 키는 필요 없어요. (7장)

---

## 0. 한눈에 보는 구조

```
mailing_service/
├─ topics/            ← ★ 주제 설정 (무엇을 모을지)
│  ├─ ai_trends.yaml     AI 동향 리포트
│  ├─ demo.yaml          체험판 (인터넷·API 키 없이 모양 확인)
│  └─ _template.yaml     새 주제용 빈 양식
├─ themes/            ← ★ 디자인 (색·글꼴·크기) — dark.yaml 하나만 고치면 디자인 변경
├─ templates/         ← 리포트 배치 양식 (머리·카드·배지·바닥 조각)
├─ reporter/          ← 공통 엔진 (주제와 무관, 보통 고칠 일 없음)
│  ├─ collectors/        수집기 (RSS·웹페이지·GitHub·arXiv·HF·Semantic Scholar)
│  ├─ delivery/          발송 채널 (web·email·kakao)
│  ├─ summarizer.py      Claude 요약
│  └─ pipeline.py        전체 흐름
├─ data/              ← 보낸 기록 (같은 소식 두 번 안 보내기)
├─ docs/              ← 웹 리포트 (GitHub Pages가 보여줌)
└─ out/               ← 미리보기 결과 (--dry-run)
```

흐름: **수집 → 중복 제거 → 걸러내기 → AI 요약 → 리포트 꾸미기 → 발송**

리포트의 항목마다 아래 내용이 들어가요. 원문을 열지 않아도 이해할 수 있게 하려는 거예요.

- **한눈에 보기 (3줄 요약)**
- **자세한 설명**: 배경 → 무엇이 바뀌었나 → 왜 중요한가
  - 논문은 여기에 더해 핵심 아이디어를 비유로 풀고, 실험 결과와 한계도 설명해요.
- **용어 풀이**

---

## 1. 설치 (처음 한 번)

1. **Python 3.11 이상**을 설치해요. https://www.python.org/downloads/ 에서 받을 수 있어요.
   설치 화면에서 **"Add python.exe to PATH"** 에 꼭 체크하세요.
2. 이 폴더에서 터미널을 열고 필요한 부품을 설치해요.

```bash
pip install -r requirements.txt
```

---

## 2. 먼저 체험해 보기 (API 키 없이)

```bash
python -m reporter --topic demo --dry-run
```

`--dry-run`을 붙이면 실제로 보내지 않고, `out/` 폴더에 미리보기 파일만 만들어요.

- `out/site/demo/reports/…-daily.html` → **웹 리포트** (브라우저로 열어 보세요)
- `out/demo-…-email.html` → **이메일 미리보기**
- `out/demo-…-kakao.json` → **카카오톡으로 보낼 내용**

---

## 3. 비밀값 넣기 (.env)

`.env.example` 파일을 복사해서 이름을 `.env`로 바꾸고, 필요한 값을 채워요.
`.env`는 git에 올라가지 않으니 안심하세요. 쓰지 않는 채널의 값은 비워 둬도 돼요.

| 값 | 어디서 받나요 | 지금 설정(카톡 + 예약 작업)에서 |
|---|---|---|
| `KAKAO_*` | 6장 참고 | **필요** |
| `REPORT_BASE_URL` | 7장 참고 (GitHub Pages 주소) | **필요** (카톡 버튼 링크) |
| `ANTHROPIC_API_KEY` | https://platform.claude.com → API Keys | 필요 없음 (예약 작업이 직접 요약) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `REPORT_EMAIL_TO` | 5장 참고 | 필요 없음 (이메일 꺼 둠) |

---

## 4. AI 동향 리포트 미리보기

```bash
python -m reporter --topic ai_trends --dry-run
```

실제 소스에서 수집하고, 소스마다 몇 건이 모였는지 화면에 보여줘요. 그다음 Claude가 요약해요.
요약 비용 없이 수집만 확인하고 싶다면 `--no-summary`를 붙이세요.

**처음 실제로 보내기 전에 한 번** 아래 명령을 실행하는 걸 추천해요.
지금 사이트에 이미 올라와 있는 글을 "본 것"으로 기록만 해 두는 명령이에요.
이렇게 하면 첫날 옛날 글이 한꺼번에 쏟아지지 않아요.

```bash
python -m reporter --topic ai_trends --mark-seen
```

실제로 보내려면 `--dry-run` 없이 실행해요.

```bash
python -m reporter --topic ai_trends
```

**두 단계로 나눠 실행하기** (예약 작업이 쓰는 방식)

```bash
python -m reporter --topic ai_trends --stage collect
```

수집만 해서 `out/ai_trends-pending.json`에 저장해요. 이 파일 안 `instructions`대로 Claude가 각 항목의 `summary`와 `one_liner`·`highlights`를 채워요.

```bash
python -m reporter --topic ai_trends --stage send
```

채워진 파일로 웹 리포트를 만들고 카톡을 보내요. 비어 있는 요약은 API 키가 있으면 API로, 없으면 간단 요약으로 채워요.

---

## 5. 이메일 설정 (Gmail) — 지금은 꺼져 있어요

쓰려면 `topics/ai_trends.yaml`의 `delivery.email.enabled`를 `true`로 바꾸세요.

Gmail은 보안 때문에 일반 비밀번호로는 프로그램에서 메일을 보낼 수 없어요.
대신 **앱 비밀번호**를 만들어 써요.

1. Google 계정 → **보안** → **2단계 인증**을 켜요.
2. https://myaccount.google.com/apppasswords 에서 앱 이름(예: `report`)을 입력하고 **만들기**를 눌러요.
3. 화면에 나온 **16자리 비밀번호**를 `.env`의 `GMAIL_APP_PASSWORD`에 넣어요. 띄어쓰기는 있어도 괜찮아요.

알아 두면 좋은 점:

- 메일에는 3줄 요약과 "왜 중요한가"만 넣어요.
- 자세한 설명은 **[자세한 설명 읽기]** 버튼을 누르면 웹 리포트에서 볼 수 있어요.
- 메일에도 전체 내용을 넣고 싶으면 설정 파일에서 `email.full_detail: true`로 바꾸세요.

---

## 6. 카카오톡 "나에게 보내기" 설정

카톡에는 **핵심 3줄 + [웹 리포트 보기] 버튼**만 보내요.
메뉴 이름은 카카오 사이트가 바뀌면서 조금 다를 수 있어요.

1. https://developers.kakao.com 에 로그인 → **내 애플리케이션** → **애플리케이션 추가하기**
2. **앱 키**에서 **REST API 키**를 복사해 `.env`의 `KAKAO_REST_API_KEY`에 넣어요.
3. **카카오 로그인**을 **활성화(ON)** 해요.
4. **Redirect URI**에 `http://localhost:5000/callback`을 등록해요.
5. **동의항목**에서 **카카오톡 메시지 전송(talk_message)**을 "선택 동의" 이상으로 설정해요.
6. **플랫폼 → Web → 사이트 도메인**에 웹 리포트 주소(예: `https://내아이디.github.io`)를 등록해요.
   이걸 해야 카톡 버튼이 동작해요.
7. (선택) **보안 → Client Secret**을 쓴다면 그 값을 `KAKAO_CLIENT_SECRET`에 넣어요.
8. 이제 처음 인증을 **딱 한 번** 해요.

```bash
python -m reporter.tools.kakao_auth
```

브라우저에 카카오 로그인 화면이 떠요. **직접 로그인하고 동의**해 주세요.
끝나면 토큰이 `.secrets/kakao_token.json`에 저장돼요.

**토큰 자동 갱신은 이렇게 동작해요**

- 토큰은 카카오가 "이 프로그램이 내 카톡으로 보내도 된다"고 허락해 준 출입증이에요.
  - **짧은 출입증**(몇 시간짜리)은 보낼 때마다 새로 받아요.
  - **긴 출입증**(약 두 달짜리)은 만료가 가까워지면 카카오가 새것을 주고, 프로그램이 자동으로 바꿔 저장해요.
- 매주 실행하면 출입증이 계속 이어져요. 오래(두 달 이상) 실행하지 않아 만료되면, 예약 작업 결과에 "재인증 필요"라고 나와요.
  그때 위 인증 명령을 다시 실행하면 돼요.

---

## 7. 자동 실행 — PC 예약 작업 (지금 쓰는 방식)

Claude 데스크톱 앱의 **예약 작업** "【매주 월요일】AI 동향 리포트 카톡 발송"이 **매주 월요일 06:30**에 실행돼요.
사이드바의 **Scheduled**에서 보거나 바꿀 수 있어요. 하는 일은 이 순서예요.

1. `--stage collect`로 지난 7일 소식 수집
2. Claude(구독)가 `summary.include_rule`에 맞지 않는 항목(기술 소식이 아닌 것)을 빼고, `summary.guide` 지침대로 초보자용 설명 작성
3. `--stage send`로 웹 리포트를 만들고 카톡 발송
4. `docs/`를 GitHub에 올려 웹 리포트 게시

알아 둘 점:

- **Claude 앱이 켜져 있어야 실행돼요.** 꺼져 있으면 다음에 앱을 켤 때 실행돼요.
- 구독 사용량에서 차감돼요. Claude API 요금은 들지 않아요.
- 쉬운 말의 정도, 비유, 글자 수 같은 글쓰기 방식은 `summary.guide`에서 바꿔요.

**웹 리포트 게시 (GitHub Pages) — 처음 한 번 설정**

카톡은 200자 제한이 있어서, 자세한 설명은 [웹 리포트 보기] 버튼으로 여는 웹페이지에 담겨요.
그래서 웹페이지를 인터넷에 올려야 해요.

1. GitHub에 **공개(Public) 저장소**를 만들고 이 폴더를 올려요. 비밀값(`.env`, `.secrets/`)은 올라가지 않아요.
2. 저장소 **Settings → Pages → Build and deployment**에서 **Deploy from a branch**를 고르고, **main** 브랜치의 **/docs** 폴더를 선택해요.
3. 웹 리포트 주소는 `https://<아이디>.github.io/<저장소이름>/`이 돼요. 이 주소를 `.env`의 `REPORT_BASE_URL`에 넣어요. 끝에 `/`를 붙이세요.
4. 이 주소의 도메인(`https://<아이디>.github.io`)을 카카오 개발자 사이트 **플랫폼 → Web**에 등록해요. (6장)

**[예비] PC를 꺼 둬도 돌리고 싶다면**

`.github/workflows/report.yml`(GitHub Actions + Claude API) 방식으로 바꿀 수 있어요. 이 방식은 Claude API 요금이 들어요(10장). 파일 맨 위 설명대로 `schedule`을 켜고, Secrets에 `ANTHROPIC_API_KEY`, `KAKAO_*`, `SECRETS_PAT` 등을 넣으면 돼요.

---

## 8. 새 주제 만들기 (예: 반도체 동향)

1. `topics/_template.yaml`을 복사해서 `topics/semiconductor.yaml`로 저장해요.
2. 아래 값을 채워요.
   - `topic: semiconductor`, `title: "반도체 동향 리포트"`
   - `sections` → `sources`에 모을 사이트를 넣어요. RSS 주소가 있으면 `type: rss`가 가장 간단해요.
   - 논문이 필요하면 `keywords`와 arXiv 분류(`categories`, 예: `eess.SP`), Semantic Scholar 분야(`fields_of_study`, 예: `Engineering`)를 바꿔요.
3. 미리보기를 해요.

```bash
python -m reporter --topic semiconductor --dry-run
```

4. 자동 실행에 추가하려면 예약 작업을 하나 더 만들고, 안내문의 `--topic ai_trends`를 새 주제 이름으로 바꿔요.

**수집 방식(type) 고르기**

| 사이트 상황 | type | 필요한 값 |
|---|---|---|
| RSS 주소가 있다 | `rss` | `url` |
| RSS가 없고 글 목록 페이지만 있다 | `webpage` | `url`, `link_pattern`(글 주소 모양) |
| 한 페이지에 날짜별 변경 기록이 쌓인다 | `webpage` + `mode: headings` | `url`, `heading_id_pattern` |
| GitHub 저장소의 새 버전 | `github_releases` | `repo` |
| 최신 논문 | `arxiv`, `hf_papers` | `categories` |
| 인용수 많은 논문 | `semantic_scholar` | `fields_of_study` |

---

## 9. 디자인 바꾸기

- 색, 글꼴, 크기, 여백은 **`themes/dark.yaml` 한 파일**에만 있어요. 웹과 이메일이 이 값을 함께 써요.
- 강조색만 바꾸고 싶다면 `colors.accent` 값 하나만 고치면 돼요.
- 새 디자인을 만들려면 이렇게 해요.
  1. `themes/dark.yaml`을 복사해 `themes/light.yaml`로 저장하고 값을 바꿔요.
  2. 주제 설정 파일에서 `theme: light`로 바꿔요.
- 카드 모양이나 배치를 바꾸려면 `templates/partials/`의 조각 파일만 고치면 돼요.
  - 머리글은 `header`, 카드는 `item_card`, 배지와 버튼은 `components`, 바닥글은 `footer` 파일이에요.

---

## 10. 비용 안내 (대략)

**지금 방식(PC 예약 작업)은 Claude 구독으로 동작해서 추가 요금이 없어요.** 아래 표는 Claude API로 요약할 때(예비 방식)의 참고 비용이에요.

요약 한 건에 원문 약 4천 토큰을 넣고 약 2천 토큰을 받는다고 가정한 계산이에요. 토큰은 AI가 글을 세는 단위예요.

| 모델 (`summary.model`) | 하루 15건 기준 한 달 |
|---|---|
| `claude-opus-5-5` (기본, 가장 정확) | 약 25달러 |
| `claude-sonnet-5-5` | 약 12달러 |
| `claude-haiku-5-5` (가장 저렴) | 약 1달러 |

실제 비용은 글 길이와 개수에 따라 달라요. 정확한 사용량은 https://platform.claude.com 에서 확인하세요.
GitHub Actions, GitHub Pages, Gmail, 카카오 API는 개인 사용 범위에서 무료예요.

---

## 11. 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `python`을 찾을 수 없음 | Python 설치 시 "Add to PATH" 체크했는지 |
| `Gmail 로그인 실패` | 일반 비밀번호가 아닌 **앱 비밀번호**인지 |
| 카톡 버튼을 눌러도 안 열림 | 카카오 개발자 사이트 **플랫폼 → Web**에 도메인 등록했는지 |
| `카카오 리프레시 토큰이 없어요` | `python -m reporter.tools.kakao_auth` 실행 |
| 특정 소스 `수집 실패 (건너뜀)` | 사이트 구조가 바뀌었을 수 있어요. 해당 소스의 `url`·`link_pattern` 확인, 또는 `enabled: false`로 잠시 끄기 |
| 새 소식이 없어서 안 보냄 | 정상이에요. 보내고 싶다면 `skip_if_empty: false` |

테스트 실행:

```bash
python -m pytest
```
