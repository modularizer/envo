# envo

**Environment variable loading utility.**

`envo` provides a powerful, type-safe way to manage environment variables in Python projects. It automatically discovers `.env` files, coerces values to appropriate types, validates against specifications, and offers both programmatic and CLI interfaces.

## Features
- **Load From Many Sources** - `.env.sample` + `.env.base` + `.other.yaml` + `c.json` + `d.toml` + `.env` + `os.environ`
- **Refs** - `ENV_VAR_B=$ENV_VAR_A`
- **Math** - `ITEM_COUNT=($MODE=="prod")?5:10`
- **Chaining** - `ENVO_EXTENDS=.env.base` `ENVO_EXTENDED_BY=.env.overrides` 
- **Auto-Coerced Types** - `env.MY_VAL # 5 <int>` automatically converts strings to `int`, `float`, `bool`, `Path`, `dict`, `list`, and more
- **Validation** - using `@min/@max/@type/etc` declarations in `sample.env`
- **Self-Documenting** - comments in the `sample.env` get loaded into the `Env` object and used/shown in commandline tools
- **CLI Tools** - for validating, configuring, etc.
- **Path Substitution** - `%` references the project root, and can be used for filepath env variables
- **Path Fallbacks** - `/file-a.txt|/file-b.txt` will use the firs path that exists
- **Multiple file formats** — Load from `.env`, `.json`, `.yaml`, and `.toml` files
- **Variable grouping** — Auto-detected from `sample.env`, helps with grabbing chunks of env variables
- **Customizable** — Override behavior with `ENVO_*` environment variables
- **Supports .py env specs** - Allow using .py files to specify default values

## How to use?

### Requirements
- Python 3.10+

### Install
```bash
pip install modularizer-envo
```

Your job is simple:
* write a `sample.env` in your project root
* let the user overwrite variables using `.env` or by running `envo config`
* load in parsed variables with `from envo import Env` and `env = Env()`


## Quick Start

### Programmatic Usage

```python
from envo import Env

# Auto-discover and load environment
env = Env()

# Access with automatic type coercion
debug = env.DEBUG          # bool
port = env.PORT            # int
db_url = env.DATABASE_URL  # str

# Or use the pre-built global instance
from envo import env
print(env.DEBUG)
```

### Using a Spec File

Create a `sample.env` file to define your environment schema:

```bash
# sample.env - Environment Variable Specification

# =============================================================================
# database - Database Configuration
# =============================================================================
DB_HOST=localhost          # Database hostname @required
DB_PORT=5432               # Port number @type:int @range:1-65535
DB_NAME=myapp              # Database name

# =============================================================================
# server - Server Configuration  
# =============================================================================
DEBUG=false                # Enable debug mode @type:bool
PORT=8080                  # Server port @type:int
LOG_LEVEL=info             # Log level @choices:debug,info,warn,error
```

Then in your code:

```python
from envo import Env

env = Env()  # Automatically uses sample.env as spec

# Values are validated and coerced according to spec
port = env.DB_PORT    # int: 5432
debug = env.DEBUG     # bool: False
```

## CLI Commands

### `envo show` - Display environment variables with colored output.
### `envo validate` - Validate a `.env` file against a spec.
### `envo config` - Interactive TUI for browsing and editing environment variables.


## Spec File Format

### Basic `.env` Spec

```bash
# =============================================================================
# group_name - Group Description
# =============================================================================

VARIABLE_NAME=default_value  # Documentation text @directive:value

# Supported directives:
#   @type:int|float|bool|str|path|json|list|glob
#   @min:N          - Minimum value
#   @max:N          - Maximum value
#   @range:N-M      - Range constraint
#   @choices:a,b,c  - Valid choices
#   @pattern:regex  - Regex pattern
#   @required       - Value must be non-empty
```

### JSON/YAML Spec

```yaml
# config.yaml
database:
  DB_HOST:
    default: localhost
    help: Database hostname
    required: true
  DB_PORT:
    default: 5432
    type: int
    min: 1
    max: 65535

server:
  DEBUG:
    default: false
    type: bool
  PORT:
    default: 8080
    type: int
```

## Type Coercion

`envo` automatically coerces values based on content or explicit type hints:

| Type          | Examples                                            | Notes                 |
|---------------|-----------------------------------------------------|-----------------------|
| `bool`        | `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off` | Case-insensitive      |
| `int`         | `42`, `1_000_000`                                   | Underscores allowed   |
| `float`       | `3.14`, `1_000.5`                                   | Underscores allowed   |
| `path`        | `/home/user`, `~/data`, `%/config`                  | `%` = project root    |
| `dict`/`list` | `{"key": "value"}`, `["a", "b"]`                    | JSON format           |
| `null`        | `null`, `none`                                      | Becomes Python `None` |

```python
# Explicit type override
env.get("PORT", type=int)
env.get("HOSTS", type=list)
env.get_as("CONFIG_PATH", Path)
```

## File Chaining

Chain multiple configuration files with priority control:

```bash
# base.env - Load another file with LOWER priority (we override it)
ENVO_EXTENDS=defaults.env
DB_HOST=production-db

# .env - Load another file with HIGHER priority (it overrides us)
ENVO_EXTENDED_BY=.env.local
```

Priority order (lowest to highest):
1. Spec file defaults (`sample.env`)
2. Extended files (`ENVO_EXTENDS`)
3. Main `.env` file
4. Extending files (`ENVO_EXTENDED_BY`)
5. System environment variables (`os.environ`)

## Variable References

Reference other variables with `$VAR_NAME`:

```bash
BASE_DIR=/app
DATA_DIR=$BASE_DIR/data
LOG_DIR=$BASE_DIR/logs
FULL_URL=http://$HOST:$PORT/api
```

Use `%` to reference the project root:

```bash
CONFIG_PATH=%/config
DATA_PATH=%/data
```

### Expression Operators

Envo supports logical and arithmetic expressions for dynamic configuration:

| Operator | Syntax | Description | Result |
|----------|--------|-------------|--------|
| Ternary | `$VAR?yes:no` | If VAR is truthy, use "yes", else "no" | `yes` or `no` |
| NOT | `!$VAR` | Logical negation | `true` or `false` |
| AND | `$A&&$B` | Logical AND | `true` or `false` |
| OR | `$A\|\|$B` | Logical OR | `true` or `false` |
| Equals | `$A==$B` | Equality check | `true` or `false` |
| Not Equals | `$A!=$B` | Inequality check | `true` or `false` |
| Add | `$A+$B` | Addition (numbers) or concatenation (strings) | number or string |
| Subtract | `$A-$B` | Subtraction | number |
| Multiply | `$A*$B` | Multiplication | number |

> **Note:** Single `|` and `/` are NOT operators to avoid conflicts with path separators.

```bash
# Ternary - conditional values
DEBUG_MSG=$DEBUG?Debugging enabled:Production mode
DB_HOST=$USE_DOCKER?db:localhost

# Logical operators (use && and ||)
IS_READY=$DB_CONFIGURED&&$CACHE_CONFIGURED
USE_FALLBACK=$PRIMARY_DOWN||$FORCE_FALLBACK
FEATURE_OFF=!$FEATURE_ENABLED

# Comparisons
IS_PROD=$ENV==production
NOT_LOCAL=$ENV!=local

# Arithmetic
TOTAL_WORKERS=$CPU_COUNT*2
ADJUSTED_PORT=$BASE_PORT+$INSTANCE_ID

# String concatenation (when values aren't both numeric)
GREETING=$HELLO+$WORLD

# Combine with parentheses
SHOW_DEBUG=($DEBUG&&$VERBOSE)||$FORCE_DEBUG
COMPLEX_CALC=($A+$B)*$C
```

**Truthiness:** Values are truthy unless they are empty, `false`, `0`, `no`, `off`, `null`, or `none`.

## Variable Groups

Filter variables by group for organized access:

```python
# Get all database variables
db_env = env.get_group("database")
print(db_env.DB_HOST)

# List all available groups
print(env.list_groups())

# Access all groups as a dict
for name, group_env in env.groups.items():
    print(f"{name}: {list(group_env.keys())}")
```

## Configuration

Customize `envo` behavior with environment variables:

| Variable                  | Default                             | Description                             |
|---------------------------|-------------------------------------|-----------------------------------------|
| `ENVO_DEFAULT_ENV_FILE`   | `.env`                              | Default env file name                   |
| `ENVO_DEFAULT_SPEC_FILES` | `sample.env,.env.sample`            | Spec file search order                  |
| `ENVO_DEFAULT_GROUP`      | `unknown`                           | Default group for ungrouped vars        |
| `ENVO_USE_SPEC_DEFAULT`   | `<default>`                         | Special value to use spec default       |
| `ENVO_BOOL_TRUE_VALUES`   | `true,1,yes,on,y,enable,enabled`    | Values coerced to `True`                |
| `ENVO_BOOL_FALSE_VALUES`  | `false,0,no,off,n,disable,disabled` | Values coerced to `False`               |
| `ENVO_PROJECT_ROOT_CHAR`  | `%`                                 | Character for project root substitution |
| `ENVO_REF_CHAR`           | `$`                                 | Character for variable references       |

See `sample.env` in the repository for the complete list of configuration options, including color scheme customization.

## Advanced Usage

### Custom Spec

```python
from envo import Env

env = Env(
    ".env",
    spec={
        "PORT": int,
        "DEBUG": bool,
        "HOSTS": list,
        "DB_*": {"groups": ("database",), "type": str},
        "API_*": {"groups": ("api",), "required": True},
    }
)
```

### Multiple Files with Priority

```python
# Load with explicit priority order
env = Env(
    "defaults.env",      # Lowest priority
    ".env",              # Medium priority
    ".env.local",        # Highest priority
)

# Control system environment handling
env = Env(
    ".env",
    existing_env_priority="lowest",  # or "highest" (default), "none"
)
```

### Validation Pipeline

```python
from envo import Env
from envo.spec_type import VariableSpec

env = Env(
    spec={
        "PORT": VariableSpec(
            type=int,
            default=8080,
            validator=lambda x: x if 1 <= x <= 65535 else ValueError("Invalid port"),
        ),
        "EMAIL": VariableSpec(
            type=str,
            pattern=r"^[^@]+@[^@]+\.[^@]+$",
            required=True,
        ),
    }
)
```

### Access Raw Values

```python
# Get the raw string value before coercion
raw_port = env.raw["PORT"]  # "8080" (string)

# Get the parsed/coerced value
port = env.PORT  # 8080 (int)
```

## License

[Unlicense](LICENSE) — Public Domain

