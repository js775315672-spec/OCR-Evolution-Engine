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

## C2 · 한국어/표/저화질 CER·WER 평가 (Draft PR #2)

- 공개된 **합성 개발용** 원본 6건(한국어 2, 3열 표 2, 저화질 2)의 정답 문장과 재현 가능한 PNG 생성기: [평가셋](benchmarks/c2_synthetic_manifest.json)
- 실제 Tesseract `kor+eng` 실행 후 **CER/WER, 케이스별 실패, 매니페스트/이미지 SHA-256**를 JSON·Markdown·PNG 아티팩트로 저장: [C2 워크플로](.github/workflows/ocr-evolution-c2.yml)
- Unicode NFC 정규화 및 Levenshtein 거리 기반, 값이 100% 초과해도 기록. Windows·Linux 계산/계약 테스트 및 Linux 실제 OCR 평가.
- 실행 방법·평가의 한계·숨겨진 독립 평가셋 선행조건은 [C2 명세](docs/OCR_EVOLUTION_C2.md) 참조.
- **중요:** 합성 개발셋의 테스트 통과는 한국어 실문서 성능이나 자율 모델 개선이 입증되었다는 뜻이 아니며, 자동 승격/병합 기능은 없음.

```sh
python -m pip install -e ".[test,benchmark]"
python -m unittest discover -s tests -p 'test_c2_metrics.py' -v
# Ubuntu + NanumGothic + Tesseract kor/eng 설치 후
python -m ocr_evolution.benchmark --font /usr/share/fonts/truetype/nanum/NanumGothic.ttf
```

## C2.1 · 실제 한국어 문서·표 구조 검증

- 실제 한국어 공개 문서: ONTHEIT/KDoc-OCRBench-V2에서 **재현 가능한 2쪽**을 선택해 Tesseract로 OCR을 수행합니다. 원본은 CI 실행 중에만 받아 사용하고, 검증된 문장·표 셀·기하학적 인접 관계만 측정합니다. 데이터 출처·권리·수정 불가능한 업스트림 커밋·문서 SHA를 보존합니다.
- 실제 스캔/카메라 사진: `ocr_evolution.real_corpus` 로컬 CLI는 파일 해시·사용권한·수동 정답 전문을 검사한 후에만 **CER/WER**를 측정합니다. 로컬 파일을 GitHub에 업로드하지 않습니다.
- 표 구조: `score_grid()`로 행/열 위치별 셀 및 인접 관계 F1을 측정합니다. 실제 공공 PDF에서는 Tesseract TSV의 상하좌우 관계 검사도 수행합니다. 이는 완전한 TEDS/병합 셀 인식과 다릅니다.
- 공개 PDF는 사람 검토를 거친 **일부 문장·셀 정답**만 제공하므로 문서 전체의 CER/WER는 `N/A`로 표시합니다. 물리적 스캔 평가 건수는 실제 입력이 있을 때만 증가합니다.
- 실제 공개문서 기준선([CI 실행](../../actions/runs/44926387420)): 2쪽, 정답 문장 3/5, 표 셀 텍스트 180/289, 방향 관계 24/917(2.62%). **엄격한 기하학적 프록시**일 뿐 표 전체 구조 F1이나 TEDS가 아닙니다. CER/WER는 전문 수동 정답이 없어 N/A입니다.
- 실제 CI: [C2.1 public OCR & table checks](.github/workflows/ocr-evolution-c21.yml) · [평가 설계·실행법](docs/OCR_EVOLUTION_C21.md).

```sh
python -m pip install -e ".[test]"
python -m unittest discover -s tests -p "test_c21*.py" -v
# 공개 문서 2쪽을 실제 실행할 때만 다음 명령 사용 (네트워크 다운로드)
python -m pip install "huggingface_hub>=0.34,<2"
OCR_REAL_DATA_NETWORK_CONSENT=1 python -m ocr_evolution.kdoc_public --sample-count 2
# 실제 개인 소유 스캔은 로컬에서만 평가
python -m ocr_evolution.real_corpus --manifest /private/ocr/manifest.json --corpus-root /private/ocr
```

**원칙:** 개발·평가 데이터가 공개되어 있어도 숨겨진 독립 평가 또는 자율 지능 향상으로 간주하지 않으며, 모델 자동 업데이트와 자동 병합은 차단합니다.

## C2.2 · 실제 촬영 한국어 OCR 및 수동 전사 정답 수집 게이트

**개발 중인 C2.2 평가 트랙은 문서 유형을 구분합니다.** 한국어 실사 촬영 간판 글자 3개([K-STR-Bench GIST-Signboard](https://huggingface.co/datasets/hoonisone/K-STR-Bench), 해당 부분집합 CC BY 4.0)를 평가하도록 구현했지만, 공식 이미지 압축 파일이 **1,427,559,424 bytes**여서 750MiB 다운로드 한도에 따라 **BLOCKED**, 현재 CER/WER는 **N/A**야. 향후 더 작은 라이선스 확인 데이터나 별도 승인된 다운로드에서만 실제 수치를 산출해. 하지만 간판은 영수증·종이 스캔 문서가 아니므로 별도 지표로만 보고합니다.

한국어 영수증 원본 후보 2개([HumynLabs](https://huggingface.co/datasets/HumynLabs/Korean_Receipts_Dataset), CC BY 4.0)는 실제 공개 이미지를 CI에서 받아 파일 해시를 기록하고, 물리적 촬영 여부 및 사람의 완전 전사문을 확인하기 전에는 CER/WER를 **N/A**로 고정합니다. 원본 이미지와 OCR 원문은 GitHub CI 아티팩트에 업로드하지 않습니다.

실제 개인 소유 사진/스캔의 CER/WER 측정에는 **동일 이미지 SHA-256에 대한 서로 다른 두 사람의 직접 시각 전사·명시적 사용 권한·촬영 방식 검증**이 필요합니다. OCR이 스스로 제안한 텍스트는 정답으로 승격할 수 없습니다. 실물 스캔 확보와 한국어 실사 간판 시험은 동일한 성과가 아닙니다.

- [실제 공개 사진 OCR 및 자료 수집 CI](.github/workflows/ocr-evolution-c22.yml)
- [실물 스캔 2인 수동 전사·권리·CER/WER 절차](docs/OCR_EVOLUTION_C22.md)
- 데이터 출처: Han & Hong (ACCV 2026) K-STR-Bench, HumynLabs Korean Receipts Dataset
- 완료 판정: Windows/Linux 계약 테스트·실제 사진 CI PASS + 실물 문서 수동 정답 및 독립 홀드아웃은 **미완료 게이트**로 분리

```sh
python -m pip install -e ".[test]"
python -m unittest discover -s tests -p "test_c22*.py" -v
# Linux: tesseract-ocr / eng / kor 와 huggingface_hub 설치 후
OCR_C22_EXTERNAL_DATA_CONSENT=1 python -m ocr_evolution.c22_public --output-dir reports/c22
# 실물 사진을 두 명이 각각 직접 전사한 다음에만:
python -m ocr_evolution.c22_review --review-request /private/ocr/reviews.json --image-root /private/ocr --out-manifest /private/ocr/audited_manifest.json
python -m ocr_evolution.real_corpus --manifest /private/ocr/audited_manifest.json --corpus-root /private/ocr --output /private/ocr/measured.json
```

**안전:** Ouroboros/Cerberus/Fenrir와 기억·실행권·데이터를 공유하지 않으며 `main` 변경·자동 병합·OCR 모델 자동 승격을 수행하지 않습니다.
