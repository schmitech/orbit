# Recommended Adapter Architecture

This document proposes a new hierarchical structure for adapters within the Orbit server to improve organization, scalability, and clarity.

## 1. Overview

Currently, adapter logic is split between two locations:
- `/server/adapters`
- `/server/retrievers/adapters`

This separation is confusing. The adapters located in `/server/retrievers/adapters` are not specific to retriever implementations but are domain-specific components used *by* retrievers to format data. This creates unclear dependencies and makes the architecture harder to scale.

The goal is to consolidate all adapter logic into a single, well-organized directory: `/server/adapters` with a unified registry system.

## 2. Proposed Hierarchical Structure

All adapters will be moved under `/server/adapters` and grouped by the **domain** they operate on. This creates a clear and scalable structure.

The proposed directory tree is as follows:

```
/server/adapters/
├── __init__.py             # Main adapter package init
├── base.py                 # Defines the base DocumentAdapter ABC
├── registry.py             # Unified ADAPTER_REGISTRY (consolidates both registry systems)
├── compatibility.py        # Backward compatibility layer for old import paths
│
├── generic/
│   ├── __init__.py
│   └── adapter.py          # Implements GenericDocumentAdapter
│
├── passthrough/
│   ├── __init__.py
│   └── adapter.py          # Implements ConversationalAdapter
│
├── file/
│   ├── __init__.py
│   └── adapter.py          # Implements FileAdapter
│
├── qa/                     # Sub-package for all Question-Answering adapters
│   ├── __init__.py
│   ├── base.py             # Implements the base QADocumentAdapter
│   ├── chroma.py           # Implements ChromaQAAdapter (datasource-specific)
│   └── sql.py              # Implements QASQLAdapter (datasource-specific)
│
└── intent/                 # Sub-package for all Intent-based adapters
    ├── __init__.py
    └── adapter.py          # Implements IntentAdapter
```

### 2.1. Relationship with Retriever Implementations

This architecture intentionally separates **Domain Adapters** from **Retriever Implementations**.

-   **Retriever Implementations (`/server/retrievers/implementations/`)**: These classes are responsible for the technical details of connecting to a data source (like ChromaDB, a PostgreSQL database, etc.) and fetching data. They will **remain** in their current location. For example, `ChromaRetriever` stays in `/server/retrievers/implementations/vector/chroma_retriever.py`.

-   **Domain Adapters (`/server/adapters/`)**: These classes are responsible for formatting the data retrieved by a retriever into a specific domain context (like QA, Intent, etc.). This refactoring moves this logic into the `/server/adapters/` directory.

**Example Workflow:**

1.  A service needs QA results from ChromaDB.
2.  It uses a `QAChromaRetriever` (the implementation) from `/server/retrievers/implementations/qa/qa_chroma_retriever.py`.
3.  The `QAChromaRetriever` inherits from both `QAVectorRetrieverBase` and `ChromaRetriever`, combining QA-specific logic with ChromaDB operations.
4.  During initialization, it creates a `ChromaQAAdapter` (the domain adapter) through the registry system from `/server/adapters/qa/chroma.py`.
5.  When retrieving data, it uses the domain adapter's methods:
    - `format_document()` to structure raw data into QA format
    - `extract_direct_answer()` to find direct answers in results
    - `apply_domain_specific_filtering()` to filter and rank results

This separation ensures that retriever implementations focus on data fetching and database operations, while the adapters handle all the domain-specific business logic for formatting, filtering, and answer extraction.

### Key Concepts:

- **`/server/adapters`**: The single source of truth for all data transformation and domain-specific adapter logic.
- **`base.py`**: Contains the abstract base class (`DocumentAdapter`) that all domain adapters will inherit from.
- **`registry.py`**: The unified `AdapterRegistry` that consolidates both hierarchical and simple registry patterns for backward compatibility.
- **`compatibility.py`**: Provides backward compatibility imports to ease migration and prevent breaking changes.
- **Domain Subdirectories (`/qa`, `/intent`, etc.)**: Each subdirectory represents a distinct operational domain. This allows for grouping related logic, including base classes and datasource-specific implementations for that domain.

## 3. Migration Plan

The following list details where existing files and classes will be moved and refactored.

### 3.1. File and Class Relocations

- **Registry:**
  - `server/retrievers/adapters/registry.py` → `server/adapters/registry.py` (enhanced with additional functionality)

- **Base Classes:**
  - `DocumentAdapter` from `server/retrievers/adapters/domain_adapters.py` → `server/adapters/base.py`
  - `DocumentAdapterFactory` from `server/retrievers/adapters/domain_adapters.py` → `server/adapters/factory.py` (may be deprecated in favor of unified registry)

- **Generic Adapter:**
  - `GenericDocumentAdapter` from `server/retrievers/adapters/domain_adapters.py` → `server/adapters/generic/adapter.py`

- **Passthrough Adapter:**
  - `ConversationalAdapter` from `server/adapters/passthrough/conversational/conversational_adapter.py` → `server/adapters/passthrough/adapter.py`

- **File Adapter:**
  - `FileAdapter` from `server/retrievers/adapters/file_adapter.py` → `server/adapters/file/adapter.py`

- **QA Adapters:**
  - `QADocumentAdapter` from `server/retrievers/adapters/domain_adapters.py` → `server/adapters/qa/base.py`
  - `ChromaQAAdapter` from `server/retrievers/adapters/qa/chroma_qa_adapter.py` → `server/adapters/qa/chroma.py`
  - `QASQLAdapter` from `server/retrievers/adapters/qa/qa_sql_adapter.py` → `server/adapters/qa/sql.py`

- **Intent Adapter:**
  - `IntentAdapter` from `server/retrievers/adapters/intent/intent_adapter.py` → `server/adapters/intent/adapter.py`

### 3.2. Import Path Updates Required

The migration will require updating **25+ import statements** throughout the codebase (exact count to be determined during implementation):

- `retrievers.adapters.registry` → `adapters.registry`
- `retrievers.adapters.domain_adapters` → `adapters.base`
- `retrievers.adapters.qa.*` → `adapters.qa.*`
- `retrievers.adapters.intent.*` → `adapters.intent.*`
- `retrievers.adapters.file_adapter` → `adapters.file.adapter`
- `adapters.passthrough.conversational.conversational_adapter` → `adapters.passthrough.adapter`

### 3.3. Registry Consolidation

The current `AdapterRegistry` already supports both hierarchical and simple patterns through its existing `create()` method. The new unified registry will enhance this functionality:

```python
class AdapterRegistry:
    def __init__(self):
        # Single registry supporting both patterns
        self._registry = {}  # type -> datasource -> adapter_name
        
    def register(self, adapter_type: str, datasource: str, adapter_name: str, 
                implementation: str = None, factory_func: Callable = None, 
                config: Dict = None):
        """Register adapter using hierarchical structure"""
        # Enhanced implementation with better error handling
        
    def create(self, adapter_type: str, datasource: str, adapter_name: str, 
              override_config: Dict = None, **kwargs):
        """Unified creation method that handles both patterns"""
        # Smart method that tries hierarchical first, then simple fallback
```

### 3.4. Backward Compatibility

A compatibility layer will be created to ease migration:

```python
# server/retrievers/adapters/__init__.py (temporary)
# Re-export from new locations for backward compatibility
from adapters.base import DocumentAdapter, DocumentAdapterFactory
from adapters.registry import ADAPTER_REGISTRY

# Re-export specific adapters for backward compatibility
from adapters.generic.adapter import GenericDocumentAdapter
from adapters.passthrough.adapter import ConversationalAdapter
from adapters.file.adapter import FileAdapter
from adapters.qa.base import QADocumentAdapter
from adapters.qa.chroma import ChromaQAAdapter
from adapters.qa.sql import QASQLAdapter
from adapters.intent.adapter import IntentAdapter
```

### 3.5. Configuration File Updates

The following configuration files may need updates to reference new adapter paths:

- `config/adapters.yaml` - Update implementation paths
- `config/config.yaml` - Update any hardcoded adapter references
- Any other config files that reference adapter implementations

Example configuration update:
```yaml
# Before
implementation: 'retrievers.adapters.domain_adapters.QADocumentAdapter'

# After  
implementation: 'adapters.qa.base.QADocumentAdapter'
```

### 3.6. Edge Case Handling

The migration plan addresses several edge cases:

- **Dynamic Adapter Imports**: Adapters that register themselves during import will continue to work through the backward compatibility layer
- **Self-Registering Adapters**: The registry system will handle adapters that register themselves automatically
- **Circular Dependencies**: The backward compatibility layer prevents import cycles during migration
- **Fallback Mechanisms**: The existing fallback patterns in `DocumentAdapterFactory` will be preserved during transition

The old directories (`/server/retrievers/adapters` and `/server/adapters/passthrough`) will be removed after the migration is complete and all imports have been updated.

## 4. Benefits of the New Structure

- **Scalability**: Easily add new domains (e.g., a new `/summary` package) or new datasource-specific implementations within an existing domain (e.g., `qa/qdrant.py`).
- **Clarity**: The purpose of each module is clear. The architecture cleanly separates data fetching (`/server/retrievers`) from data transformation and domain logic (`/server/adapters`).
- **Maintainability**: Decoupling adapters from retrievers and clarifying dependencies will make the codebase easier to understand, maintain, and test. Import paths will become more consistent and logical (e.g., `from server.adapters.base import DocumentAdapter`).

## 5. Implementation Steps

1.  Create the new directory structure under `/server/adapters`.
2.  Create the unified registry system that consolidates both existing registry patterns.
3.  Move the files and classes to their new locations as outlined above.
4.  Create backward compatibility layer to prevent breaking changes.
5.  Perform a project-wide update of all import statements that reference the moved modules.
6.  Update configuration files that reference adapter paths.
7.  Run comprehensive tests to ensure no regressions.
8.  Delete the now-empty `server/retrievers/adapters/` and `server/adapters/passthrough/` directories.

## 6. Future Adapter Extensibility

The proposed architecture is designed to be adaptable and can easily accommodate the future adapter types described in the roadmap, such as the `HTTP` and `Vision` adapters.

The core principle of organizing adapters by their operational domain allows for seamless expansion. Here is how the new adapters would be integrated:

```
/server/adapters/
├── __init__.py
├── base.py                 # Defines base DocumentAdapter
├── registry.py             # Global ADAPTER_REGISTRY
│
├── generic/
│   └── adapter.py
├── passthrough/
│   └── adapter.py
├── file/
│   └── adapter.py
│
├── qa/
│   ├── base.py
│   ├── chroma.py
│   └── sql.py
│
├── intent/
│   └── adapter.py
│
├── http/                   # <-- NEW: For the HTTP Adapter
│   ├── __init__.py
│   ├── base.py             # Defines a base HTTPAdapter
│   ├── rest.py             # Implementation for REST
│   └── graphql.py          # Implementation for GraphQL
│
└── vision/                 # <-- NEW: For the Vision Adapter
    ├── __init__.py
    ├── base.py             # Defines a base VisionAdapter
    └── adapter.py          # Main implementation
```

Adding a new adapter type becomes as simple as creating a new subdirectory. This approach keeps the concerns of each adapter type cleanly separated, which aligns with the distinct processing architectures outlined in the roadmap document.

## 7. Gradual Implementation Milestones

To safely introduce these architectural changes, a milestone-based approach is recommended. Each milestone represents a distinct, testable, and committable set of changes.

### Milestone 1: Establish New Structure and Core Components
The goal of this step is to create the foundational directories and move the most critical, widely-used components without migrating the adapters themselves.

1.  **Action**: Create the new directory structure under `/server/adapters`, including subdirectories like `generic`, `passthrough`, `file`, `qa`, `intent`, etc.
2.  **Action**: Enhance the existing `AdapterRegistry` in `server/adapters/registry.py` with improved error handling and fallback mechanisms.
3.  **Action**: Move the `DocumentAdapter` abstract base class from `server/retrievers/adapters/domain_adapters.py` to `server/adapters/base.py`.
4.  **Action**: Move the `DocumentAdapterFactory` from `server/retrievers/adapters/domain_adapters.py` to `server/adapters/factory.py` (consider deprecation).
5.  **Action**: Create backward compatibility layer in `server/retrievers/adapters/__init__.py` to re-export from new locations.
6.  **Action**: Update all import statements across the project that reference the moved `AdapterRegistry` and `DocumentAdapter`.
7.  **Action**: Handle edge cases like dynamic imports and self-registering adapters.
8.  **Test**: Run the full test suite. The system should function identically, as only file locations and import paths for core components have changed.
9.  **Commit**: `refactor(architecture): Establish new adapter structure and move core components`

### Milestone 2: Migrate Generic and Simple Adapters
Migrate the self-contained adapters that have fewer dependencies.

1.  **Action**: Move `GenericDocumentAdapter` to `server/adapters/generic/adapter.py`.
2.  **Action**: Move `ConversationalAdapter` to `server/adapters/passthrough/adapter.py`.
3.  **Action**: Move `FileAdapter` to `server/adapters/file/adapter.py`.
4.  **Action**: Update the `AdapterRegistry` and any direct imports to reflect the new locations.
5.  **Action**: Update backward compatibility layer to include new adapter locations.
6.  **Action**: Delete the now-empty `/server/adapters/passthrough/conversational` directory.
7.  **Test**: Run tests, focusing on retrievers that use the "generic", "conversational", or "file" adapters.
8.  **Commit**: `refactor(adapters): Migrate generic, passthrough, and file adapters`

### Milestone 3: Migrate QA Adapters
This milestone focuses on the more complex QA domain, which has a base class and datasource-specific implementations.

1.  **Action**: Move `QADocumentAdapter` to `server/adapters/qa/base.py`.
2.  **Action**: Move `ChromaQAAdapter` to `server/adapters/qa/chroma.py`.
3.  **Action**: Move `QASQLAdapter` to `server/adapters/qa/sql.py`.
4.  **Action**: Update all imports and registry registrations for these QA adapters.
5.  **Action**: Update backward compatibility layer to include QA adapter locations.
6.  **Action**: Delete the old `/server/retrievers/adapters/qa/` directory.
7.  **Test**: Run all tests related to QA retrievers to ensure they correctly load and use their domain adapters from the new location.
8.  **Commit**: `refactor(adapters): Migrate QA adapters to new domain structure`

### Milestone 4: Migrate Intent Adapters
This milestone handles the intent domain.

1.  **Action**: Move `IntentAdapter` from `/server/retrievers/adapters/intent/intent_adapter.py` to `/server/adapters/intent/adapter.py`.
2.  **Action**: Update all relevant imports and registrations.
3.  **Action**: Update backward compatibility layer to include intent adapter locations.
4.  **Action**: Delete the old `/server/retrievers/adapters/intent/` directory.
5.  **Test**: Run tests for intent-based retrievers.
6.  **Commit**: `refactor(adapters): Migrate intent adapters to new domain structure`

### Milestone 5: Final Cleanup
The final step is to remove all remnants of the old structure.

1.  **Action**: The `server/retrievers/adapters/domain_adapters.py` file should now be empty or nearly empty. Remove it.
2.  **Action**: The `server/retrievers/adapters/` directory should now be empty. Delete it.
3.  **Action**: Remove the backward compatibility layer from `server/retrievers/adapters/__init__.py`.
4.  **Action**: Perform a final project-wide search for any import paths still pointing to `server.retrievers.adapters` and correct them.
5.  **Action**: Update any configuration files that reference old adapter paths.
6.  **Test**: Run the full regression test suite one last time.
7.  **Commit**: `refactor(architecture): Finalize adapter migration and remove old directories`

## 8. Testing Strategy

Each milestone includes comprehensive testing to ensure no regressions:

### 8.1. Test Categories
- **Unit Tests**: Individual adapter functionality
- **Integration Tests**: Adapter-retriever interactions
- **Registry Tests**: Registry creation and lookup functionality
- **Import Tests**: Verify all import paths work correctly
- **Configuration Tests**: Ensure config files reference correct paths

### 8.2. Test Commands
```bash
# Run full test suite
pytest ./server/tests/ -v

# Run adapter-specific tests
pytest ./server/tests/test_*adapter*.py -v

# Run retriever integration tests
pytest ./server/tests/test_*retriever*.py -v

# Run registry tests
pytest ./server/tests/test_*registry*.py -v
```

### 8.3. Pre-Migration Testing
Before starting migration:
1. Run full test suite and document baseline results
2. Create test data for all adapter types
3. Verify all current functionality works

### 8.4. Post-Milestone Testing
After each milestone:
1. Run full test suite
2. Compare results with baseline
3. Test specific functionality for migrated adapters
4. Verify registry functionality

## 9. Rollback Plan

In case of issues during migration:

### 9.1. Milestone-Level Rollback
Each milestone can be rolled back independently:
- Revert the specific commit for that milestone
- Restore files from backup
- Run tests to verify rollback success

### 9.2. Emergency Rollback
If critical issues arise:
1. Revert to the last known good commit
2. Restore the old directory structure
3. Verify all functionality works
4. Investigate and fix issues before retrying

### 9.3. Backup Strategy
Before starting migration:
1. Create a full backup of the current codebase
2. Tag the current state as `pre-adapter-migration`
3. Document current test results

## 10. Risk Mitigation

### 10.1. High-Risk Areas
- **Registry consolidation**: Complex logic with multiple dependencies
- **Import path updates**: 25+ files need updating
- **Factory pattern changes**: DocumentAdapterFactory may need deprecation
- **Dynamic adapter imports**: Adapters that register themselves during import
- **Circular dependencies**: Potential import cycles during migration

### 10.2. Mitigation Strategies
- **Incremental changes**: Small, testable commits
- **Backward compatibility**: Maintain old import paths during transition
- **Comprehensive testing**: Test after each change
- **Documentation**: Document all changes and decisions

### 10.3. Success Criteria
- All tests pass
- No performance regression
- All existing functionality preserved
- Clean, maintainable code structure

## 11. Implementation Timeline

### 11.1. Estimated Timeline
- **Milestone 1**: 3-4 days (Core structure and registry)
- **Milestone 2**: 2-3 days (Simple adapters)
- **Milestone 3**: 3-4 days (QA adapters)
- **Milestone 4**: 2-3 days (Intent adapters)
- **Milestone 5**: 1-2 days (Cleanup)

**Total Estimated Time**: 11-16 days

### 11.2. Dependencies
- Each milestone depends on the previous one
- Registry consolidation must be completed before adapter migration
- Backward compatibility layer must be maintained throughout

### 11.3. Resource Requirements
- Developer familiar with the codebase
- Access to test environment
- Backup and rollback capabilities

## 12. Post-Migration Benefits

### 12.1. Immediate Benefits
- Clear separation of concerns
- Consistent import paths
- Easier to understand architecture
- Better maintainability

### 12.2. Long-term Benefits
- Easier to add new adapter types
- Better testability
- Reduced coupling between components
- Improved code organization

### 12.3. Future Extensibility
The new structure makes it trivial to add:
- New domain adapters (e.g., `/summary`, `/translation`)
- New datasource-specific implementations
- New adapter types (HTTP, Vision, etc.)
- Cross-cutting concerns (logging, metrics, etc.)