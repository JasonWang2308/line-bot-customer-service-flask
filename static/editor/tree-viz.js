/*
 * editor/tree-viz.js — D3 橫向樹狀圖
 *
 * 定位:
 *   依目前 menuData 渲染可拖曳 / 縮放 / 點選的橫向樹狀圖到 #tree-svg。
 *   點節點 → 跳到「編輯」分頁並選取該節點 (透過 selectNode + switchTab)。
 *   只負責畫圖；不修改 menuData。
 *
 * 包含單元 (units):
 *   drawTreeViz               對外入口；組合下面的 helpers
 *   _setupSvg                 清空 / 設定 viewBox / 取容器尺寸
 *   _setupGradients           為節點底色定義 linearGradient
 *   _setupZoom                pan + zoom 行為與初始位移
 *   _layoutTree               d3.hierarchy + d3.tree() 算位置
 *   _drawLinks                繪製連線 + dasharray draw-in 動畫
 *   _drawNodes                繪製節點 + scale/opacity 進場 + hover/click 行為
 *   _highlightAncestorPath    hover 時標記從 root 到此節點的所有 link
 *   _pathToD3Node             D3 hierarchy node → menuData 路徑
 *   _samePathFromD3           判斷 D3 節點是否為當前選取
 */

const _NODE_W = 160;
const _NODE_H = 38;

function drawTreeViz() {
  const svg = d3.select("#tree-svg");
  const { height } = _setupSvg(svg);
  _setupGradients(svg);

  const g = svg.append("g");
  _setupZoom(svg, g, height);

  const root = _layoutTree(menuData);
  _drawLinks(g, root);
  _drawNodes(g, root);
}

function _setupSvg(svg) {
  svg.on(".zoom", null);
  svg.selectAll("*").remove();
  const container = svg.node().parentElement;
  const width = container.clientWidth;
  const height = container.clientHeight;
  svg.attr("viewBox", `0 0 ${width} ${height}`).attr("preserveAspectRatio", "xMidYMid meet");
  return { width, height };
}

function _setupGradients(svg) {
  const defs = svg.append("defs");
  const branch = defs.append("linearGradient")
    .attr("id", "gradient-branch")
    .attr("x1", "0%").attr("y1", "0%").attr("x2", "0%").attr("y2", "100%");
  branch.append("stop").attr("offset", "0%").attr("stop-color", "#f0f6ff");
  branch.append("stop").attr("offset", "100%").attr("stop-color", "#e3effb");

  const leaf = defs.append("linearGradient")
    .attr("id", "gradient-leaf")
    .attr("x1", "0%").attr("y1", "0%").attr("x2", "0%").attr("y2", "100%");
  leaf.append("stop").attr("offset", "0%").attr("stop-color", "#fff7ed");
  leaf.append("stop").attr("offset", "100%").attr("stop-color", "#fed7aa");
}

function _setupZoom(svg, g, height) {
  const zoom = d3.zoom()
    .scaleExtent([0.2, 3])
    .on("zoom", (e) => g.attr("transform", e.transform));
  svg.call(zoom);
  svg.call(zoom.transform, d3.zoomIdentity.translate(80, height / 2));
}

function _layoutTree(menuData) {
  const root = d3.hierarchy(menuData, (d) => d.children);
  const layout = d3.tree().nodeSize([_NODE_H + 16, _NODE_W + 80]);
  layout(root);
  return root;
}

function _drawLinks(g, root) {
  const linkPath = d3.linkHorizontal().x((d) => d.y).y((d) => d.x);

  const links = g.selectAll(".link")
    .data(root.links())
    .enter()
    .append("path")
    .attr("class", "link")
    .attr("d", linkPath);

  // dasharray 動畫，依深度 stagger
  links.each(function () {
    const len = this.getTotalLength();
    d3.select(this)
      .attr("stroke-dasharray", `${len} ${len}`)
      .attr("stroke-dashoffset", len)
      .transition()
      .duration(700)
      .delay((d) => 250 + d.target.depth * 180)
      .ease(d3.easeCubicOut)
      .attr("stroke-dashoffset", 0)
      .on("end", function () {
        d3.select(this).attr("stroke-dasharray", null);
      });
  });
}

function _drawNodes(g, root) {
  const nodeG = g.selectAll(".node")
    .data(root.descendants())
    .enter()
    .append("g")
    .attr("transform", (d) => `translate(${d.y},${d.x})`)
    .attr("opacity", 0)
    .style("transform-box", "fill-box")
    .style("transform-origin", "center");

  nodeG.transition()
    .duration(450)
    .delay((d) => d.depth * 180)
    .ease(d3.easeBackOut.overshoot(1.3))
    .attr("opacity", 1);

  nodeG.append("rect")
    .attr("class", (d) => `node-rect ${nodeKind(d.data)}` + (_samePathFromD3(d) ? " selected" : ""))
    .attr("x", -_NODE_W / 2)
    .attr("y", -_NODE_H / 2)
    .attr("width", _NODE_W)
    .attr("height", _NODE_H)
    .attr("rx", 10)
    .on("click", (e, d) => {
      const path = _pathToD3Node(d);
      selectNode(path);
      switchTab("edit");
    })
    .on("mouseenter", function (e, d) {
      d3.select(this).transition().duration(150).attr("transform", "scale(1.08)");
      _highlightAncestorPath(g, d);
    })
    .on("mouseleave", function () {
      d3.select(this).transition().duration(150).attr("transform", "scale(1)");
      g.selectAll(".link").classed("highlight", false);
    });

  nodeG.append("title").text((d) => `${d.data.label} [${kindLabel(nodeKind(d.data))}]`);
  nodeG.append("text")
    .attr("class", "node-text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .text((d) => truncate(d.data.label, 14));
}

function _highlightAncestorPath(g, d) {
  const ancestorIds = new Set();
  let cur = d;
  while (cur.parent) {
    ancestorIds.add(`${cur.parent.data.label}->${cur.data.label}`);
    cur = cur.parent;
  }
  g.selectAll(".link").classed("highlight", function (l) {
    return ancestorIds.has(`${l.source.data.label}->${l.target.data.label}`);
  });
}

function _pathToD3Node(d3node) {
  const path = [];
  let cur = d3node;
  while (cur.parent) {
    path.unshift(cur.parent.children.indexOf(cur));
    cur = cur.parent;
  }
  return path;
}

function _samePathFromD3(d3node) {
  return samePath(_pathToD3Node(d3node), selectedPath);
}
