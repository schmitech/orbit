## 1. Audit & Define Boundaries

1. **Map out responsibilities**

   * **Configuration loading & resolution** (`load_config`, `_resolve_*` methods)
   * **Logging setup** (`_setup_initial_logging`, `_setup_logging`)
   * **Provider resolution** (`_resolve_datasource_embedding_provider`, `_resolve_component_provider`, `_resolve_component_model`)
   * **Service initialization & shutdown** (`_initialize_services`, `_shutdown_services`, lifecycle manager)
   * **Dependency definitions** (`get_chat_service`, `get_health_service`, etc.)
   * **Endpoint registration** (all the `@self.app.*` routes)
   * **Utility setup** (CORS, SSL context, atexit hooks)
2. **Define module boundaries**

   * `config/`
   * `logging_setup/`
   * `providers/`
   * `services/`
   * `routers/`
   * `dependencies/`
   * `lifespan/`
   * `main.py` (or `app.py`) to wire everything up

---

## 2. Extract Configuration Logic → `config/`

* **Move** `load_config` invocation and all `_resolve_*` methods into a `config/manager.py` and `config/providers.py`.
* **Expose** a single `Config` class or pydantic `Settings` that on instantiation reads env, applies overrides, and exposes resolved values.

> Benefits: centralizes config handling, makes it easy to swap in tests or new backends.&#x20;

---

## 3. Extract Logging Setup → `logging_setup/`

* **Create** `logging_setup/initial.py` for `_setup_initial_logging`.
* **Create** `logging_setup/full.py` for `_setup_logging`.
* **Provide** a simple function `configure_logging(config)` that main or lifespan code can call before any imports that log.

> Benefits: you can test logging config in isolation and avoid cluttering main server code.&#x20;

---

## 4. Extract Provider Resolution → `providers/`

* **Group** `_resolve_datasource_embedding_provider`, `_resolve_component_provider`, and `_resolve_component_model` into utility functions in `providers/resolver.py`.
* **Expose** a higher-level API like `resolve_all_providers(config)` that returns a dict of resolved providers/models.

> Benefits: keeps provider logic decoupled from server lifecycle.&#x20;

---

## 5. Service Initialization & Shutdown → `services/initializer.py`

* **Turn** `_initialize_services` and `_shutdown_services` into two functions: `async def init_services(app, config)` and `async def shutdown_services(app)`.
* **Inside** that module, import each service class and perform the same logic (MongoDB, API key, Prompt, Guardrail, RAG retriever, etc).

> Benefits: you can call these from FastAPI’s lifespan events without a giant class.&#x20;

---

## 6. Split Out Routers → `routers/`

* **For each group of endpoints**, create an `APIRouter` in its own file:

  * `routers/chat.py` → `/v1/chat` logic
  * `routers/admin_api_keys.py` → `/admin/api-keys/*`
  * `routers/prompts.py` → `/admin/prompts/*`
  * `routers/health.py` → `/health`
  * `routers/static.py` → `/favicon.ico`
* **In each**, inject dependencies via `Depends(...)` imported from a `dependencies/` module.
* **In main**, do `app.include_router(chat_router)`, etc.

> Benefits: easy to locate and modify a single API surface.&#x20;

---

## 7. Centralize Dependencies → `dependencies/`

* **Define** providers for `get_chat_service`, `get_health_service`, `get_api_key`, `validate_session_id`, etc.
* **Export** them so routers don’t need to re-declare inline dependency functions.

> Benefits: DRYs up route files and makes testing single endpoints simpler.&#x20;

---

## 8. Lifespan Management → `lifespan/manager.py`

* **Create** an `asynccontextmanager` in its own file to wire up startup/shutdown:

  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      await init_services(app, config)
      yield
      await shutdown_services(app)
  ```
* **In main**, pass that into `FastAPI(lifespan=lifespan)` instead of embedding large methods in `InferenceServer`.

> Benefits: separates lifecycle concerns from server logic.&#x20;

---

## 9. Simplify `main.py` / `app.py`

* **In `main.py`**, just do:

  ```python
  from fastapi import FastAPI
  from config.manager import Config
  from logging_setup.full import configure_logging
  from lifespan.manager import lifespan
  from routers import chat_router, admin_router, health_router, prompt_router, static_router
  from dependencies import cors_middleware, ssl_context

  config = Config()
  configure_logging(config)
  app = FastAPI(lifespan=lifespan, title="Open Inference Server", version="1.0.0")
  cors_middleware(app)
  app.include_router(...)
  ```
* **Remove** almost all code from `server.py`, leaving only the minimal import/bootstrapping logic.

---

## 10. Write Tests & CI Checks

* **Unit-test** each module (config, providers, logging) by injecting fake configs.
* **Integration tests** for each router using FastAPI’s `TestClient`, mocking services.
* **Add linting** to enforce module boundaries.

---

**Goals:**

* Clear separation of concerns
* Smaller files (<300 LOC each)
* Easier to onboard new contributors
* Enables isolated unit testing
* Simplifies future extensions (e.g. adding new routers, services, or providers)
