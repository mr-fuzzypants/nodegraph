# NodeGraph AI Instructions

## 🗺 Application Architecture

This is a **polyglot node-based graph execution engine** implemented in **Python**, **TypeScript**, and **Rust**. The implementations share core concepts but operate independently or as ports of the same logic.

### Core Concepts (Shared)
- **Node**: The fundamental unit of computation. Base class for all operations.
- **NodeNetwork**: A composite `Node` that contains a `Graph` of other nodes (subgraphs). It acts as both a Node (can be placed in a graph) and a Graph Factory.
- **Graph**: A collection of nodes and edges (using an ID-based Arena pattern in TS/Rust).
- **Port**: Connection points on nodes.
    - **Data Ports**: Pass values/objects (Inputs/Outputs).
    - **Control Ports**: Manage execution flow (signals).
- **Executor**: Separate engine that traverses the graph and executes nodes. It handles signal propagation and data flow.

### Directory Structure
- **`python/`**: The reference implementation and compiler.
    - `core/`: Base classes (`Node`, `NodeNetwork`, `Executor`, `GraphPrimitives`).
    - `compiler/`: Transforms graphs into executable code (Python, Wasm, AssemblyScript).
    - `noderegistry/`: Central node repository.
    - `examples/`: Example graph constructions.
- **`typescript/`**: Async-first implementation for Web/Node.js.
    - `src/core/`: TypeScript port of the core logic.
    - `ui/`: React + Vite frontend for visualizing/editing graphs.
- **`rust/`**: High-performance implementation (experimental/in-progress).

## 🚀 Key Workflows

### Python
- **Run Examples**: Execute scripts in `python/` root (e.g., `python python/gesture_recognition_example.py`). Note: Scripts often modify `sys.path` to include local modules.
- **Tests**: Run with `pytest`.
    ```bash
    # Run all tests
    pytest python/test/
    ```
- **New Node Creation**:
    1. Inherit from `Node` or `NodeNetwork`.
    2. Decorate with `@PluginRegistry.register("TypeName")`.
    3. Implement `create_ports(self)` to define `InputDataPort`, `OutputControlPort`, etc.
    4. Implement `execute(self, context)` for logic.

### TypeScript
- **Setup**: `cd typescript && npm install`.
- **Tests**: `npm test` (uses Jest).
    ```bash
    # Run specific test suite
    npm test NodeCookingFlow
    ```
- **UI Dev**: `cd typescript/ui && npm install && npm run dev`.
- **New Node Creation**:
    1. Extend `Node`.
    2. Register via `Node.register("TypeName")(Class)` (decorator pattern simulation).
    3. Use strictly typed interfaces (`INode`, `INodePort`).

### Rust
- **Tests**: `cargo test` inside `rust/` directory.

## 🛠 Project Conventions

- **Node Registration**: All implementations use a registry pattern. Always register new node types to make them instantiable by the factory/graph loader.
    - *Python*: `@PluginRegistry.register`
    - *TS*: `Node.register`
- **Port Naming**: Use string keys for ports. Consistency across languages is preferred if nodes are to be distinct.
- **Separation of Concerns**: Keep `Node` definitions separate from `Executor` logic. Nodes generally shouldn't "know" about the global graph state, only their inputs/outputs.
- **Factory Pattern**: Use `PluginRegistry.create_node` (Python) or similar factories to instantiate nodes by string type name.

## ⚠️ Gotchas

- **Path Imports (Python)**: The project uses explicit relative imports in `core`. When running scripts, ensure `python/` is in `PYTHONPATH` or run from root module style if set up (currently scripts use `sys.path` hacks or direct execution).
- **Async (TS)**: The TS implementation is async (`Promise<IExecutionResult>`). Python is synchronous in core but may use `asyncio` in specific runners/examples.
- **Compiler**: The `python/compiler` module is advanced usage for generating standalone code; standard execution is interpreted via `Executor.py`.
