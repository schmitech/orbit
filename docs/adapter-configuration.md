# Adapter Configuration Management

## Overview

ORBIT supports external adapter configuration files to make adapter management more maintainable. This allows you to separate adapter definitions from the main configuration file, making it easier to manage large numbers of adapters.

## Configuration Structure

### Main Configuration File (`config.yaml`)

Add an import statement at the top of your main configuration file:

```yaml
# Import external configuration files
import: "adapters.yaml"

general:
  port: 3000
  verbose: true
  # ... other general settings
  adapter: "qa-vector-chroma"  # Specify which adapter to use by default
```

### Adapter Configuration File (`adapters.yaml`)

Create a separate file for all your adapter definitions:

```yaml
# Adapter configurations for ORBIT
# This file contains all adapter definitions and can be imported by config.yaml

adapters:
  - name: "qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"
    config:
      confidence_threshold: 0.3
      max_results: 5
      return_results: 3
      # ... other config options

  - name: "qa-vector-chroma"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAChromaRetriever"
    config:
      confidence_threshold: 0.3
      distance_scaling_factor: 200.0
      embedding_provider: null
      max_results: 5
      return_results: 3

  # ... more adapters
```

## Import Features

### Multiple Import Files

You can import multiple files by specifying them as a list:

```yaml
import: 
  - "adapters.yaml"
  - "custom-adapters.yaml"
  - "experimental-adapters.yaml"
```

### Nested Imports

Imported files can also contain their own import statements, allowing for hierarchical configuration:

```yaml
# adapters.yaml
import: "vector-adapters.yaml"

adapters:
  - name: "qa-sql"
    # ... sql adapter config
```

```yaml
# vector-adapters.yaml
adapters:
  - name: "qa-vector-chroma"
    # ... vector adapter config
```

### Configuration Precedence

When importing multiple files, the configuration follows these precedence rules:

1. **Main config file** - Highest precedence
2. **Last imported file** - Second highest precedence  
3. **First imported file** - Lowest precedence

This means that if the same adapter is defined in multiple files, the definition in the main config file will take precedence.

## Benefits

### Maintainability
- **Separation of Concerns**: Keep adapter configurations separate from system settings
- **Easier Management**: Large adapter configurations don't clutter the main config
- **Version Control**: Track adapter changes independently

### Organization
- **Logical Grouping**: Group related adapters in separate files
- **Team Collaboration**: Different teams can manage different adapter files
- **Environment-Specific**: Use different adapter files for different environments

### Scalability
- **Modular Design**: Add new adapters without touching the main config
- **Reusability**: Share adapter configurations across projects
- **Testing**: Test adapter configurations in isolation

## Best Practices

### File Organization
```
config/
├── config.yaml          # Main configuration
├── adapters.yaml        # Production adapters
├── dev-adapters.yaml    # Development adapters
└── test-adapters.yaml   # Test adapters
```

### Naming Conventions
- Use descriptive file names: `production-adapters.yaml`, `qa-adapters.yaml`
- Include environment or purpose in the filename
- Use consistent naming patterns across your organization

### Version Control
- Commit adapter files separately from main config
- Use meaningful commit messages for adapter changes
- Consider using branches for experimental adapter configurations

### Documentation
- Document the purpose of each adapter file
- Include comments explaining complex adapter configurations
- Maintain a README for the configuration structure

## Migration from Single File

If you're migrating from a single `config.yaml` file:

1. **Extract adapters**: Move the `adapters:` section to `adapters.yaml`
2. **Add import**: Add `import: "adapters.yaml"` to the top of `config.yaml`
3. **Test**: Verify that all adapters are loaded correctly
4. **Remove old section**: Delete the original `adapters:` section from `config.yaml`

## Troubleshooting

### Import File Not Found
```
WARNING - Import file not found: /path/to/adapters.yaml
```
- Check that the file path is correct relative to the main config file
- Ensure the file exists and has proper permissions

### Configuration Conflicts
If you see unexpected behavior after importing:
- Check for duplicate adapter names across imported files
- Verify configuration precedence rules
- Use the configuration summary logs to see which adapters are loaded

### Performance Considerations
- Import processing happens at startup
- Large numbers of imported files may impact startup time
- Consider caching strategies for frequently changing adapter configurations 