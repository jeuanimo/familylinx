(() => {
  const container = document.getElementById("tree-container");
  if (!container) return;

  const dataUrl = container.dataset.url;
  const familyId = container.dataset.family;

  function buildTree(nodes, edges) {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const children = new Map(); // parentId -> Set(childId)
    const hasParent = new Set();

    edges
      .filter((e) => e.type === "PARENT_CHILD")
      .forEach((e) => {
        if (!children.has(e.source)) children.set(e.source, new Set());
        children.get(e.source).add(e.target);
        hasParent.add(e.target);
      });

    const roots = nodes.filter((n) => !hasParent.has(n.id));
    if (roots.length === 0 && nodes.length) roots.push(nodes[0]); // fallback

    const toDTree = (id) => {
      const n = byId.get(id);
      const childIds = Array.from(children.get(id) || []);
      return {
        name: n?.name || `Person ${id}`,
        personId: id,
        class: n?.is_living ? "living" : "deceased",
        children: childIds.map(toDTree),
      };
    };

    return roots.map((r) => toDTree(r.id));
  }

  function render(treeData) {
    dTree.init(treeData, {
      target: "#tree-container",
      height: 600,
      width: container.clientWidth || 800,
      callbacks: {
        nodeClick: function (name, extra) {
          if (extra && extra.personId) {
            window.location.href = `/families/${familyId}/people/${extra.personId}/`;
          }
        },
      },
    });
  }

  async function load() {
    container.innerHTML = "<p class='text-muted p-3'>Loading tree…</p>";
    try {
      const res = await fetch(dataUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const treeData = buildTree(data.nodes || [], data.edges || []);
      if (!treeData.length) {
        container.innerHTML = "<p class='text-muted p-3'>No people found yet.</p>";
        return;
      }
      container.innerHTML = "";
      render(treeData);
    } catch (err) {
      console.error(err);
      container.innerHTML = "<p class='text-danger p-3'>Could not load tree data.</p>";
    }
  }

  load();
})();
