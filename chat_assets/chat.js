let bridge = null;
new QWebChannel(qt.webChannelTransport, channel => { bridge = channel.objects.chat; });
marked.setOptions({ gfm: true, breaks: false });
mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict", htmlLabels: false,
  flowchart: { htmlLabels: false }, suppressErrorRendering: true, fontFamily: "Arial, sans-serif" });
const root = document.getElementById("messages");
let diagramId = 0;
let diagramPayload = null;

function button(text, action, className = "") {
  const element = document.createElement("button");
  element.type = "button"; element.textContent = text; element.className = className;
  element.addEventListener("click", action); return element;
}
function copy(text, control) {
  if (bridge) bridge.copy(text);
  control.textContent = "Copiato";
  setTimeout(() => { if (control.isConnected) control.textContent = "Copia"; }, 1200);
}
function codeHeader(language, source) {
  const header = document.createElement("div"); header.className = "block-header";
  const caption = document.createElement("span"); caption.className = "language"; caption.textContent = language || "Codice";
  header.append(caption);
  const control = button("Copia", () => copy(source, control)); header.append(control);
  return header;
}
async function renderDiagram(container, source) {
  const rendered = await mermaid.render("george-diagram-" + (++diagramId), source, container);
  if (!container.isConnected) return null;
  container.innerHTML = DOMPurify.sanitize(rendered.svg, { USE_PROFILES: { svg: true, svgFilters: true } });
  return container.querySelector("svg");
}
function enhanceMarkdown(body, streaming) {
  body.querySelectorAll("img, iframe, object, embed, form").forEach(node => node.remove());
  body.querySelectorAll("a").forEach(link => {
    link.removeAttribute("target");
    link.addEventListener("click", event => { event.preventDefault(); if (bridge) bridge.openLink(link.href); });
  });
  body.querySelectorAll("table").forEach(table => {
    const scroll = document.createElement("div"); scroll.className = "table-scroll";
    table.replaceWith(scroll); scroll.append(table);
  });
  body.querySelectorAll("pre > code").forEach(code => {
    const source = code.textContent;
    const language = (code.className.match(/language-([^\s]+)/) || ["", ""])[1].toLowerCase();
    const pre = code.parentElement;
    const block = document.createElement("section"); block.className = "code-block";
    pre.replaceWith(block); block.append(codeHeader(language, source), pre);
    if (language === "mermaid" && !streaming) {
      block.className = "diagram-block";
      const canvas = document.createElement("div"); canvas.className = "diagram-canvas"; block.append(canvas);
      renderDiagram(canvas, source).then(svg => {
        if (!svg || !block.isConnected) return;
        pre.hidden = true;
        const header = block.querySelector(".block-header"); header.querySelector(".language").textContent = "Diagramma";
        header.append(button("Codice", () => { pre.hidden = !pre.hidden; }));
        header.append(button("Espandi", () => { if (bridge) bridge.expandDiagram(source); }));
      }).catch(() => {
        canvas.remove();
        const error = document.createElement("div"); error.className = "diagram-error";
        error.textContent = "Diagramma non valido: puoi consultare e copiare il codice."; block.append(error);
      });
    } else if (language !== "mermaid") {
      if (language && hljs.getLanguage(language)) code.innerHTML = hljs.highlight(source, { language }).value;
      else code.innerHTML = hljs.highlightAuto(source).value;
    }
  });
  renderMathInElement(body, { throwOnError: false, trust: false,
    delimiters: [{left:"$$",right:"$$",display:true},{left:"\\[",right:"\\]",display:true},
      {left:"\\(",right:"\\)",display:false},{left:"$",right:"$",display:false}] });
}
function updateMessage(node, role, text, streaming) {
  if (node.dataset.role === role && node._source === text && node._streaming === streaming) return;
  node.dataset.role = role; node._source = text; node._streaming = streaming;
  const user = role === "Tu"; node.className = "message " + (user ? "user" : "assistant"); node.replaceChildren();
  const header = document.createElement("div"); header.className = "message-header";
  const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = user ? "" : "✦";
  const label = document.createElement("span"); label.textContent = role;
  header.append(avatar, label);
  if (!streaming) {
    const control = button("Copia", () => copy(text, control), "copy-response"); header.append(control);
  }
  const body = document.createElement("div"); body.className = "body";
  if (user) body.textContent = text;
  else {
    body.innerHTML = DOMPurify.sanitize(marked.parse(text), { USE_PROFILES: { html: true },
      FORBID_TAGS: ["style", "img", "iframe", "object", "embed", "form", "input", "button"] });
  }
  node.append(header, body);
  if (!user) enhanceMarkdown(body, streaming);
}
async function expandedDiagram(source) {
  root.replaceChildren(); root.className = "diagram-mode";
  const header = codeHeader("Diagramma", source), canvas = document.createElement("div"); canvas.className = "diagram-canvas";
  root.append(header, canvas);
  try {
    const svg = await renderDiagram(canvas, source);
    if (!svg) return;
    const box = svg.viewBox.baseVal; let scale = 1;
    function zoom(value) { scale = value; svg.style.width = Math.max(100, box.width * scale) + "px"; svg.style.height = "auto"; }
    function fit() { zoom(Math.min((canvas.clientWidth - 36) / box.width, (canvas.clientHeight - 36) / box.height, 1.5)); }
    header.append(button("−", () => zoom(Math.max(.2, scale / 1.25))),
      button("+", () => zoom(Math.min(6, scale * 1.25))), button("Adatta", fit)); fit();
  } catch (_) { canvas.textContent = "Non è stato possibile mostrare il diagramma."; }
}
window.renderChat = payload => {
  if (payload.diagram) {
    if (diagramPayload !== payload.diagram) { diagramPayload = payload.diagram; expandedDiagram(payload.diagram); }
    return;
  }
  const pinned = payload.forceScroll || document.documentElement.scrollHeight - window.scrollY - window.innerHeight < 90;
  const messages = payload.messages.map(([role, text]) => ({ role, text, streaming: false }));
  if (payload.answer) messages.push({ role: "Antigravity", text: payload.answer, streaming: payload.busy });
  root.querySelectorAll(".thinking").forEach(node => node.remove());
  while (root.children.length > messages.length) root.lastElementChild.remove();
  messages.forEach((message, index) => {
    let node = root.children[index];
    if (!node) { node = document.createElement("article"); root.append(node); }
    updateMessage(node, message.role, message.text, message.streaming);
  });
  if (payload.busy) {
    const indicator = document.createElement("div"); indicator.className = "thinking";
    indicator.textContent = payload.answer ? "Sta scrivendo…" : "Sta pensando…"; root.append(indicator);
  }
  if (pinned) requestAnimationFrame(() => window.scrollTo(0, document.documentElement.scrollHeight));
};
