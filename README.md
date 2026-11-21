# OCR Evolution Engine v1.1

PDF 원본과 로컬 OCR 결과를 페이지별로 대조하는 독립 프로젝트입니다.

## 개발 및 성능 대시보드

| 항목 | 상태 또는 측정 기준 |
| --- | --- |
| PDF → 렌더링 → OCR → SQLite → 비교 화면 | MVP 구현 |
| G0 독립성 | 보호 저장소 연결·공유 저장소·워크플로 일정 검사 및 별도 DB 격리 테스트 |
| Python 3.11 CI | [OCR checks](../../actions/workflows/ci.yml)의 `ocr-test-results` 아티팩트 |
| 한 페이지 처리 시간 | CI 영어 고정 샘플에서 렌더링 + 실제 OCR 시간을 ms로 기록 |
| 업로드 처리 시간 | 결과 API와 UI의 `elapsed_ms`에 전체 페이지 렌더링 + OCR 시간 표시. 업로드와 DB 저장 제외 |
| 정확도와 속도 추세 | 한국어·표·저화질 평가 세트와 반복 측정 기준선 미수립 |

## 실행

Python 3.11과 PATH에 등록된 Tesseract가 필요합니다. 운영체제에 맞는 Tesseract와 언어팩을 설치하세요. 기본 언어는 `eng`이며 한국어를 함께 쓰려면 `kor` 언어팩을 설치하고 환경변수 `OCR_LANGUAGE=eng+kor`를 설정하세요.

```sh
python -m venv .venv
# 가상 환경 활성화 후
python -m pip install -e ".[test]"
python -m uvicorn ocr_engine.app:create_app --factory --host 127.0.0.1 --port 8000
python -m unittest discover -v
```

브라우저에서 `http://127.0.0.1:8000`을 여세요. 원본 페이지에 단어 좌표를 표시하고, 같은 페이지의 인식 텍스트를 옆에 보여줍니다. PDF 원본은 다운로드할 수 있습니다.

## 데이터 계약과 운영 범위

- `POST /api/documents`에 `application/pdf` 본문을 전송합니다. 최대 16 MiB, 12페이지이며 암호화된 PDF는 거부합니다. 업로드와 OCR은 서버 프로세스당 한 건씩 처리합니다.
- `GET /api/documents/{id}`는 원본 SHA-256, 엔진과 언어, 처리 시간, 페이지별 인식 결과를 반환합니다. 페이지 번호는 1부터 시작합니다. 좌표는 렌더링 이미지의 왼쪽 위를 원점으로 하는 픽셀 단위이고, 신뢰도는 0~100입니다.
- `OCR_DB_PATH`로 DB 파일을 지정할 수 있습니다. 기본 위치는 `ocr-data/ocr.sqlite3`입니다. PDF 바이트, 페이지 PNG, 단어 좌표와 신뢰도를 한 트랜잭션으로 저장합니다.
- `OCREngine` 프로토콜의 `recognize(png)`를 구현하면 앱 생성 시 다른 로컬 엔진을 주입할 수 있습니다.
- 로컬 단일 사용자 실행을 전제로 합니다. PDF는 로컬에서 처리하며 서버를 루프백에 바인딩합니다. PDF 파싱 자체는 앱 프로세스 안에서 실행됩니다.

## G0 감사 기준

개발 시작 시 읽기 전용으로 기록한 `main` 커밋입니다.

| 저장소 | 시작 SHA |
| --- | --- |
| OCR-Evolution-Engine | `dfa8d8830c370bb01714741d4227a66934e8f9a2` |
| Harness-Ouroboros-MCP | `6b44c67a4f69cdc7cbbd983356e5795a551b48fc` |
| Cerberus | `bdc1589516f0348e23efe0a61d3cac163ce5be29` |
| Fenrir-Agent | `b1454fc9bab573b7018103cce35e9a443b68dfd4` |
