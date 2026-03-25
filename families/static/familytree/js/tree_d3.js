window.FamilyTreeRenderers = window.FamilyTreeRenderers || {};

(function registerD3Renderer() {
  const dx = 120; // vertical spacing
  const dy = 260; // horizontal spacing
  const boxW = 190;
  const boxH = 74;

  function normalizeData(raw) {
    const nodes = raw?.nodes || [];
    // Prefer parentChildLinks shape (interactive API), fall back to edges/links
    const pcLinks = raw?.parentChildLinks || raw?.edges || raw?.links || [];
    const parentChildEdges = pcLinks.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type || "PARENT_CHILD",
    }));
    const spouseLinksRaw = raw?.spouseLinks || [];
    const spouseEdges = spouseLinksRaw.map((e) => ({
      source: e.source,
      target: e.target,
    }));
    return { nodes, parentChildEdges, spouseEdges };
  }

  function buildComponents(nodes, parentChildEdges, spouseEdges) {
    const adj = new Map();
    nodes.forEach((n) => adj.set(String(n.id), new Set()));
    parentChildEdges.forEach((e) => {
      if (!adj.has(String(e.source)) || !adj.has(String(e.target))) return;
      adj.get(String(e.source)).add(String(e.target));
      adj.get(String(e.target)).add(String(e.source));
    });
    spouseEdges.forEach((e) => {
      if (!adj.has(String(e.source)) || !adj.has(String(e.target))) return;
      adj.get(String(e.source)).add(String(e.target));
      adj.get(String(e.target)).add(String(e.source));
    });

    const visited = new Set();
    const components = [];
    nodes.forEach((n) => {
      const id = String(n.id);
      if (visited.has(id)) return;
      const comp = [];
      const stack = [id];
      while (stack.length) {
        const cur = stack.pop();
        if (visited.has(cur)) continue;
        visited.add(cur);
        comp.push(cur);
        (adj.get(cur) || []).forEach((nbr) => {
          if (!visited.has(nbr)) stack.push(nbr);
        });
      }
      components.push(comp);
    });
    return components;
  }

  function filterToComponent(nodes, parentChildEdges, spouseEdges, focusId) {
    const components = buildComponents(nodes, parentChildEdges, spouseEdges);
    const focusStr = focusId ? String(focusId) : null;
    let targetComp = null;
    if (focusStr) {
      targetComp = components.find((c) => c.includes(focusStr));
    }
    if (!targetComp) {
      // pick the largest component
      targetComp = components.sort((a, b) => b.length - a.length)[0] || [];
    }
    const allowed = new Set(targetComp || []);
    const filteredNodes = nodes.filter((n) => allowed.has(String(n.id)));
    const filteredParentEdges = parentChildEdges.filter(
      (e) => allowed.has(String(e.source)) && allowed.has(String(e.target))
    );
    const filteredSpouseEdges = spouseEdges.filter(
      (e) => allowed.has(String(e.source)) && allowed.has(String(e.target))
    );
    return { filteredNodes, filteredParentEdges, filteredSpouseEdges };
  }

  function buildHierarchy(nodes, edges, rootIds) {
    const rootIdStrs = new Set(Array.from(rootIds || []).map((v) => String(v)));
    const byId = new Map(nodes.map((n) => [n.id, { ...n, children: [] }]));
    const hasParent = new Set();

    edges.forEach((e) => {
      if (e.type !== "PARENT_CHILD") return;
      // Keep focus roots as roots even if they have parents
      if (rootIdStrs.has(String(e.target))) return;
      const parent = byId.get(e.source);
      const child = byId.get(e.target);
      if (parent && child) {
        parent.children.push(child);
        hasParent.add(child.id);
      }
    });

    // Roots are nodes without a parent; fallback to first node
    const roots = nodes.filter((n) => rootIdStrs.has(String(n.id)) || !hasParent.has(n.id));
    return roots.length ? roots : nodes.slice(0, 1);
  }

  function pickSingleRoot(roots, focusId) {
    if (!roots || roots.length === 0) return null;
    if (roots.length === 1) return roots[0];

    const focusStr = focusId ? String(focusId) : null;

    const containsFocus = (node) => {
      if (!focusStr) return false;
      if (String(node.id) === focusStr) return true;
      if (!node.children) return false;
      return node.children.some((c) => containsFocus(c));
    };

    const countDesc = (node) => {
      let total = 1;
      (node.children || []).forEach((c) => {
        total += countDesc(c);
      });
      return total;
    };

    // Prefer subtree containing focus
    if (focusStr) {
      const withFocus = roots.find((r) => containsFocus(r));
      if (withFocus) return withFocus;
    }

    // Otherwise pick largest
    let best = roots[0];
    let bestSize = countDesc(best);
    roots.forEach((r) => {
      const sz = countDesc(r);
      if (sz > bestSize) {
        best = r;
        bestSize = sz;
      }
    });
    return best;
  }

  function render(treeNodes, { container, familyId, focusId }) {
    container.innerHTML = "";
    const width = container.clientWidth || 900;
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

    const g = svg.append("g").attr("transform", `translate(120,${dx / 2})`);

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

    // Card background (like interactive boxes)
    node
      .append("rect")
      .attr("x", -boxW / 2)
      .attr("y", -boxH / 2)
      .attr("width", boxW)
      .attr("height", boxH)
      .attr("rx", 10)
      .attr("ry", 10)
      .attr("fill", (d) => {
        const gcode = (d.data.gender || "").toUpperCase();
        if (gcode === "M") return "#e3f2fd";
        if (gcode === "F") return "#fce4ec";
        return "#f8fafc";
      })
      .attr("stroke", (d) => {
        const gcode = (d.data.gender || "").toUpperCase();
        if (gcode === "M") return "#1976d2";
        if (gcode === "F") return "#c2185b";
        return "#cbd5e1";
      })
      .attr("stroke-width", 1.6);

    // Name line
    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "-0.1em")
      .attr("fill", "#0f172a")
      .attr("font-weight", 700)
      .attr("font-size", 14)
      .text((d) => d.data.name || "Unknown");

    // Dates line
    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "1.15em")
      .attr("fill", "#475569")
      .attr("font-size", 12)
      .text((d) => {
        const birth = d.data.birth_year || (d.data.birth_date ? d.data.birth_date.slice(0, 4) : "");
        const death = d.data.death_year || (d.data.death_date ? d.data.death_date.slice(0, 4) : "");
        if (!birth && !death) return "";
        if (birth && death) return `b. ${birth} · d. ${death}`;
        if (birth) return `b. ${birth}`;
        return `d. ${death}`;
      });

    // If a focusId is provided, re-center the viewBox around that node
    if (focusId) {
      const target = node.data().find((d) => String(d.data.id) === String(focusId));
      if (target) {
        const padX = 350;
        const padY = 200;
        const vx = Math.max(0, target.y - padX);
        const vy = target.x - padY;
        const vw = padX * 2;
        const vh = padY * 2;
        svg.attr("viewBox", [vx, vy, vw, vh].join(" "));
      }
    }
  }

  async function load({ container, dataUrl, familyId, inlineData, focusId }) {
    container.innerHTML = "<p class='text-muted p-3'>Loading tree…</p>";

    const useData = async () => {
      if (!inlineData || typeof inlineData !== "object") {
        throw new Error("No tree data available");
      }
      const { nodes, parentChildEdges, spouseEdges } = normalizeData(inlineData);

      // Narrow to the component containing the focus (or the largest)
      const { filteredNodes, filteredParentEdges, filteredSpouseEdges } = filterToComponent(
        nodes,
        parentChildEdges,
        spouseEdges,
        focusId
      );

      // Decide which IDs should be treated as roots: focus + one spouse (if any)
      const rootIds = new Set();
      if (focusId) {
        rootIds.add(String(focusId));
        const spouse = filteredSpouseEdges.find(
          (s) => String(s.source) === String(focusId) || String(s.target) === String(focusId)
        );
        if (spouse) {
          const other =
            String(spouse.source) === String(focusId) ? spouse.target : spouse.source;
          rootIds.add(String(other));
        }
      }

      const hierarchyRoots = buildHierarchy(filteredNodes, filteredParentEdges, rootIds);
      if (!hierarchyRoots.length) {
        container.innerHTML = "<p class='text-muted p-3'>No people found yet.</p>";
        return;
      }
      const singleRoot = pickSingleRoot(hierarchyRoots, focusId);
      const rootsToRender = singleRoot ? [singleRoot] : hierarchyRoots;
      render(rootsToRender, { container, familyId, focusId });
    };

    try {
      // First try inline data if present
      if (inlineData && typeof inlineData === "object") {
        await useData();
        return;
      }

      // Fallback to fetch
      const res = await fetch(dataUrl, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      inlineData = await res.json();
      await useData();
    } catch (err) {
      console.error(err);
      const message = err?.message || "Unknown error";
      container.innerHTML = `<p class='text-danger p-3'>Could not load tree data. ${message}</p>`;
    }
  }

  window.FamilyTreeRenderers.renderD3 = (container, inlineData = null) =>
    load({
      container,
      dataUrl: container.dataset.url,
      familyId: container.dataset.family,
      inlineData,
      focusId: container.dataset.focus || null,
    });
})();
