(() => {
  const container = document.getElementById("tree-container");
  if (!container) return;

  const dataUrl = container.dataset.url;
  const familyId = container.dataset.family;

  const width = container.clientWidth || 900;
  const dx = 90;
  const dy = 220;

  function buildHierarchy(nodes, edges) {
    const byId = new Map(nodes.map((n) => [n.id, { ...n, children: [] }]));
    const hasParent = new Set();

    edges
      .filter((e) => e.type === "PARENT_CHILD")
      .forEach((e) => {
        const parent = byId.get(e.source);
        const child = byId.get(e.target);
        if (parent && child) {
          parent.children.push(child);
          hasParent.add(child.id);
        }
      });

    // Roots are nodes without a parent; fallback to first node
    const roots = nodes.filter((n) => !hasParent.has(n.id));
    return roots.length ? roots : nodes.slice(0, 1);
  }

  function render(treeNodes) {
    container.innerHTML = "";
    const rootData = { name: "root", children: treeNodes };
    const root = d3.hierarchy(rootData);
    const tree = d3.tree().nodeSize([dx, dy]);
    tree(root);

    const x0 = d3.min(root.descendants(), (d) => d.x) - dx;
    const x1 = d3.max(root.descendants(), (d) => d.x) + dx;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("viewBox", [0, x0, width, x1 - x0 + dx].join(" "))
      .style("width", "100%")
      .style("height", "100%")
      .style("font", "14px Inter, system-ui, sans-serif");

    const g = svg.append("g").attr("transform", `translate(50,${dx / 2})`);

    // Links
    g.append("g")
      .attr("fill", "none")
      .attr("stroke", "#cbd5e1")
      .attr("stroke-width", 1.5)
      .selectAll("path")
      .data(root.links())
      .join("path")
      .attr("d", d3.linkHorizontal().x((d) => d.y).y((d) => d.x));

    // Nodes
    const node = g
      .append("g")
      .attr("stroke-linejoin", "round")
      .attr("stroke-width", 1.5)
      .selectAll("g")
      .data(root.descendants())
      .join("g")
      .attr("transform", (d) => `translate(${d.y},${d.x})`)
      .attr("cursor", (d) => (d.data.id ? "pointer" : "default"))
      .on("click", (event, d) => {
        if (d.data.id) {
          window.location.href = `/families/${familyId}/people/${d.data.id}/`;
        }
      });

    // Photo clips
    node
      .append("defs")
      .append("clipPath")
      .attr("id", (d, i) => `clip-${i}`)
      .append("circle")
      .attr("r", 22);

    // Photo / fallback
    node
      .append("circle")
      .attr("r", 26)
      .attr("fill", "#f8fafc")
      .attr("stroke", "#cbd5e1");

    node
      .filter((d) => d.data.photo)
      .append("image")
      .attr("href", (d) => d.data.photo)
      .attr("x", -22)
      .attr("y", -22)
      .attr("width", 44)
      .attr("height", 44)
      .attr("clip-path", (d, i) => `url(#clip-${i})`);

    node
      .filter((d) => !d.data.photo)
      .append("text")
      .attr("dy", "0.35em")
      .attr("text-anchor", "middle")
      .attr("fill", "#475569")
      .text((d) => {
        const name = d.data.name || "";
        const parts = name.trim().split(/\s+/);
        return parts.slice(0, 2).map((p) => p[0] || "").join("").toUpperCase() || "•";
      });

    node
      .append("text")
      .attr("dy", "3.1em")
      .attr("text-anchor", "middle")
      .attr("fill", "#0f172a")
      .attr("font-weight", 600)
      .text((d) => d.data.name || "Unknown");

    node
      .append("text")
      .attr("dy", "4.7em")
      .attr("text-anchor", "middle")
      .attr("fill", "#64748b")
      .attr("font-size", 12)
      .text((d) => {
        const birth = d.data.birth_date ? `b. ${d.data.birth_date.slice(0, 4)}` : "";
        const death = d.data.death_date ? `d. ${d.data.death_date.slice(0, 4)}` : "";
        return [birth, death].filter(Boolean).join(" · ");
      });
  }

  async function load() {
    container.innerHTML = "<p class='text-muted p-3'>Loading tree…</p>";
    try {
      const res = await fetch(dataUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const hierarchyRoots = buildHierarchy(data.nodes || [], data.edges || []);
      if (!hierarchyRoots.length) {
        container.innerHTML = "<p class='text-muted p-3'>No people found yet.</p>";
        return;
      }
      render(hierarchyRoots);
    } catch (err) {
      console.error(err);
      container.innerHTML = "<p class='text-danger p-3'>Could not load tree data.</p>";
    }
  }

  load();
})();
