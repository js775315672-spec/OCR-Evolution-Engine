const form = document.querySelector("#upload");
const input = document.querySelector("#pdf");
const button = document.querySelector("#submit");
const status = document.querySelector("#status");
const panel = document.querySelector("#result");
const picker = document.querySelector("#page");
const boxes = document.querySelector("#boxes");
const canvas = document.querySelector("#preview");
const words = document.querySelector("#words");
const original = document.querySelector("#original");
let result;
let viewVersion = 0;

async function showPage() {
  const version = ++viewVersion;
  const page = result.pages[Number(picker.value)];
  words.textContent = page.words.map(word => word.text).join(" ") || "인식된 텍스트 없음";
  canvas.width = page.width;
  canvas.height = page.height;
  const image = new Image();
  image.src = `/api/documents/${result.id}/pages/${page.number}`;
  try {
    await image.decode();
    if (version !== viewVersion) return;
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    if (boxes.checked) {
      context.strokeStyle = "#08795d";
      context.lineWidth = 2;
      for (const word of page.words) context.strokeRect(word.x, word.y, word.width, word.height);
    }
  } catch {
    if (version === viewVersion) status.textContent = "원본 페이지를 불러오지 못했습니다.";
  }
}

async function checkedJson(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "요청에 실패했습니다.");
  return data;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const file = input.files[0];
  if (!file) return;
  button.disabled = true;
  panel.hidden = true;
  ++viewVersion;
  status.textContent = "로컬 OCR 처리 중…";
  try {
    const upload = await fetch("/api/documents", {
      method: "POST", headers: {"Content-Type": "application/pdf"}, body: file,
    }).then(checkedJson);
    result = await fetch(`/api/documents/${upload.id}`).then(checkedJson);
    picker.replaceChildren(...result.pages.map((page, index) => new Option(page.number, index)));
    original.href = `/api/documents/${result.id}/original`;
    status.textContent = `${result.engine} (${result.language}) · ${result.pages.length}페이지 · ${result.elapsed_ms} ms`;
    panel.hidden = false;
    await showPage();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

picker.addEventListener("change", showPage);
boxes.addEventListener("change", showPage);
