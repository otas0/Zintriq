(function (root) {
  const listeners = [];
  let inputBound = null;

  function emit(kind, payload) {
    listeners.slice().forEach(function (fn) {
      try {
        fn(kind, payload);
      } catch (_err) {
        /* plugin listeners must not break the engine */
      }
    });
  }

  const store = {
    code: "",
    events: "",
    preview: null,
    slug: "",
    visual: null,
    get: function () {
      return {
        code: this.code,
        events: this.events,
        preview: this.preview,
        slug: this.slug,
        visual: this.visual,
      };
    },
    set: function (patch) {
      Object.keys(patch || {}).forEach(function (key) {
        if (key in store && key !== "get" && key !== "set") store[key] = patch[key];
      });
      emit("store", store.get());
    },
  };

  const history = {
    applying: false,
    index: -1,
    stack: [],
    push: function (snap) {
      if (this.applying) return;
      const next = snap || store.get();
      const prev = this.stack[this.index];
      if (prev && prev.code === next.code && prev.slug === next.slug && prev.events === next.events) return;
      this.stack = this.stack.slice(0, this.index + 1);
      this.stack.push({ code: next.code, events: next.events, slug: next.slug });
      if (this.stack.length > 40) this.stack.shift();
      this.index = this.stack.length - 1;
      emit("history", { index: this.index, length: this.stack.length });
    },
    undo: function () {
      if (this.index <= 0) return null;
      this.index -= 1;
      return this.stack[this.index];
    },
    redo: function () {
      if (this.index + 1 >= this.stack.length) return null;
      this.index += 1;
      return this.stack[this.index];
    },
    clear: function () {
      this.applying = false;
      this.index = -1;
      this.stack = [];
    },
  };

  const selection = {
    ids: [],
    primary: function () {
      return this.ids[0] || "";
    },
    set: function (ids) {
      this.ids = (ids || []).filter(Boolean);
      emit("selection", this.ids.slice());
    },
    clear: function () {
      this.set([]);
    },
  };

  const commands = {};
  const commandOwners = {};
  const command = {
    list: function () {
      return Object.keys(commands).map(function (id) {
        return Object.assign({ id: id }, commands[id].meta || {});
      });
    },
    register: function (id, fn, meta, owner) {
      if (!id || typeof fn !== "function") return;
      commands[id] = { fn: fn, meta: meta || {}, owner: owner || "" };
      if (owner) {
        if (!commandOwners[owner]) commandOwners[owner] = [];
        if (commandOwners[owner].indexOf(id) < 0) commandOwners[owner].push(id);
      }
    },
    run: function (id, arg) {
      const row = commands[id];
      if (!row) return null;
      command._recent = [id].concat((command._recent || []).filter(function (item) { return item !== id; })).slice(0, 8);
      if (root.ZintriqWorkbench) {
        if (typeof root.ZintriqWorkbench.setRecentForWorkspace === "function") {
          root.ZintriqWorkbench.setRecentForWorkspace(command._recent);
        } else {
          root.ZintriqWorkbench._recentCommands = command._recent;
        }
        if (typeof root.ZintriqWorkbench.persistDock === "function" && typeof root.ZintriqWorkbench.snapshotLayout === "function") {
          root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
        }
      }
      return row.fn(arg);
    },
    unregister: function (id) {
      const row = commands[id];
      delete commands[id];
      if (row && row.owner && commandOwners[row.owner]) {
        commandOwners[row.owner] = commandOwners[row.owner].filter(function (item) {
          return item !== id;
        });
      }
    },
    unregisterOwner: function (owner) {
      const ids = (commandOwners[owner] || []).slice();
      ids.forEach(function (id) {
        delete commands[id];
      });
      delete commandOwners[owner];
    },
  };

  function onKeydown(ev) {
    const target = ev.target;
    const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
    if ((ev.metaKey || ev.ctrlKey) && String(ev.key || "").toLowerCase() === "z" && !typing) {
      ev.preventDefault();
      command.run(ev.shiftKey ? "history.redo" : "history.undo");
    }
  }

  const input = {
    bind: function () {
      if (document.documentElement.getAttribute("data-engine-input") === "1") return;
      document.documentElement.setAttribute("data-engine-input", "1");
      inputBound = onKeydown;
      document.addEventListener("keydown", inputBound);
    },
    unbind: function () {
      if (inputBound) {
        document.removeEventListener("keydown", inputBound);
        inputBound = null;
      }
      document.documentElement.removeAttribute("data-engine-input");
    },
  };

  const meta = {
    boundary: function () {
      return command.run("meta.space");
    },
    describe: function () {
      return store.preview;
    },
    instantiate: function () {
      return command.run("meta.instantiate");
    },
    simulate: function () {
      return command.run("meta.step");
    },
  };

  root.ZintriqEngine = {
    command: command,
    history: history,
    input: input,
    meta: meta,
    on: function (fn) {
      if (typeof fn !== "function") return function () {};
      listeners.push(fn);
      return function () {
        const index = listeners.indexOf(fn);
        if (index >= 0) listeners.splice(index, 1);
      };
    },
    off: function (fn) {
      const index = listeners.indexOf(fn);
      if (index >= 0) listeners.splice(index, 1);
    },
    selection: selection,
    store: store,
    dispose: function () {
      listeners.length = 0;
      Object.keys(commands).forEach(function (id) {
        delete commands[id];
      });
      Object.keys(commandOwners).forEach(function (owner) {
        delete commandOwners[owner];
      });
      history.clear();
      selection.clear();
      input.unbind();
      store.set({ code: "", events: "", preview: null, slug: "", visual: null });
    },
  };
  if (root.zintriq) root.zintriq.engine = root.ZintriqEngine;
})(window);
