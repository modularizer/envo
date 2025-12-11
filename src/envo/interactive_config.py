"""
Interactive configuration editor for envo.

Provides an interactive TUI for browsing and editing environment variables
with arrow key navigation and a detailed edit view.
"""

import re
import sys
from pathlib import Path
from typing import Optional, Any

from prompt_toolkit.keys import Keys
from termite import subprint

from envo.env import Env, find_default_spec, find_default_env
from envo.load import load_single_env_raw, resolve_var_references
from envo.coerce import coerce
from envo.parse_spec import env_file_to_spec
from envo.cli import _escape_brackets
import envo.consts as consts

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Layout,
    HSplit,
    Window,
    FormattedTextControl,
)
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText


def _get_key_style(status: str, highlighted: bool = False) -> str:
    """Get the style for a key based on its status - matches envo show termite colors."""
    if highlighted:
        if status == consts.KEY_STATUS_DEFAULT:
            return consts.KEY_COLOR_DEFAULT_HIGHLIGHT
        elif status == consts.KEY_STATUS_VALID:
            return f"{consts.KEY_COLOR_VALID_HIGHLIGHT} bold"
        elif status == consts.KEY_STATUS_INVALID:
            return f"{consts.KEY_COLOR_INVALID_HIGHLIGHT} bold"
        elif status == consts.KEY_STATUS_EXTRA:
            return consts.KEY_COLOR_EXTRA_HIGHLIGHT
        else:
            return f"{consts.KEY_COLOR_DEFAULT_VALUE_HIGHLIGHT} bold"
    else:
        if status == consts.KEY_STATUS_DEFAULT:
            return consts.KEY_COLOR_DEFAULT
        elif status == consts.KEY_STATUS_VALID:
            return f"{consts.KEY_COLOR_VALID} bold"
        elif status == consts.KEY_STATUS_INVALID:
            return f"{consts.KEY_COLOR_INVALID} bold"
        elif status == consts.KEY_STATUS_EXTRA:
            return consts.KEY_COLOR_EXTRA
        else:
            return f"{consts.KEY_COLOR_DEFAULT_VALUE} bold"


def _get_value_style(value, highlighted: bool = False) -> str:
    """Get the appropriate style name for a value based on its type - matches envo show termite colors."""
    if highlighted:
        if value is None:
            return consts.VALUE_COLOR_DIM_HIGHLIGHT
        if isinstance(value, bool):
            return consts.VALUE_COLOR_GREEN_HIGHLIGHT if value else consts.VALUE_COLOR_RED_HIGHLIGHT
        if isinstance(value, (int, float)):
            return consts.VALUE_COLOR_YELLOW_HIGHLIGHT
        if isinstance(value, str):
            if '/' in value or value.startswith('~'):
                return consts.VALUE_COLOR_BLUE_HIGHLIGHT
        return consts.VALUE_COLOR_WHITE_HIGHLIGHT
    else:
        if value is None:
            return consts.VALUE_COLOR_DIM
        if isinstance(value, bool):
            return consts.VALUE_COLOR_GREEN if value else consts.VALUE_COLOR_RED
        if isinstance(value, (int, float)):
            return consts.VALUE_COLOR_YELLOW
        if isinstance(value, str):
            if '/' in value or value.startswith('~'):
                return consts.VALUE_COLOR_BLUE
        # For white/default, return empty string (no special color)
        return consts.VALUE_COLOR_WHITE if consts.VALUE_COLOR_WHITE else ""


def format_variable_line(key: str, value, key_status: str, selected: bool = False, has_unsaved_changes: bool = False, saved_value=None) -> "FormattedText":
    """Format a variable line for display in the list - matches envo show colors."""
    escaped_key = _escape_brackets(key)
    escaped_value = _escape_brackets(str(value)) if value is not None else ""
    escaped_saved_value = _escape_brackets(str(saved_value)) if saved_value is not None else consts.UI_NOT_SET
    
    key_style = _get_key_style(key_status, highlighted=selected)
    value_style = _get_value_style(value, highlighted=selected)
    saved_value_style = _get_value_style(saved_value, highlighted=selected)
    
    # Add italic for unsaved changes
    italic_prefix = "italic " if has_unsaved_changes else ""
    
    if selected:
        # Selected item - highlight that works in both light and dark mode
        parts = []
        # Add asterisk for unsaved changes
        if has_unsaved_changes:
            parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} bold", "*"))
        else:
            parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR}", " "))
        # Key with style (using highlight-specific colors)
        if key_style:
            parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}{key_style}", escaped_key))
        else:
            parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}bold", escaped_key))
        parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}", " = "))
        # Value display - show saved value in strikethrough if unsaved changes
        if has_unsaved_changes:
            # Show saved value in strikethrough using prompt_toolkit's strike style
            strike_style = f"bg:{consts.HIGHLIGHT_BG_COLOR} strike"
            if saved_value_style:
                strike_style = f"bg:{consts.HIGHLIGHT_BG_COLOR} strike {saved_value_style}"
            parts.append((strike_style, escaped_saved_value))
            parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR}", consts.UI_CHANGE_ARROW))
            # Show new value
            if value is not None:
                if value_style:
                    parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}{value_style}", escaped_value))
                else:
                    parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}", escaped_value))
            else:
                parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {italic_prefix}{consts.HIGHLIGHT_TEXT_COLOR_DIM}", consts.UI_NOT_SET))
        else:
            # Normal value display
            if value is not None:
                if value_style:
                    parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {value_style}", escaped_value))
                else:
                    parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR}", escaped_value))
            else:
                parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR} {consts.HIGHLIGHT_TEXT_COLOR_DIM}", consts.UI_NOT_SET))
        parts.append((f"bg:{consts.HIGHLIGHT_BG_COLOR}", " "))
    else:
        # Normal item - use same colors as envo show
        parts = []
        # Add asterisk for unsaved changes
        if has_unsaved_changes:
            parts.append(("bold", "*"))
            parts.append(("", " "))
        else:
            parts.append(("", "  "))
        # Key with style - match envo show termite colors
        if key_style:
            parts.append((f"{italic_prefix}{key_style}", escaped_key))
        else:
            parts.append((f"{italic_prefix}ansicyan bold", escaped_key))
        parts.append((f"{italic_prefix}", " = "))
        # Value display - show saved value in strikethrough if unsaved changes
        if has_unsaved_changes:
            # Show saved value in strikethrough using prompt_toolkit's strike style
            strike_style = "strike"
            if saved_value_style:
                strike_style = f"strike {saved_value_style}"
            parts.append((strike_style, escaped_saved_value))
            parts.append(("", consts.UI_CHANGE_ARROW))
            # Show new value
            if value is not None:
                if value_style:
                    parts.append((f"{italic_prefix}{value_style}", escaped_value))
                else:
                    parts.append((f"{italic_prefix}", escaped_value))
            else:
                parts.append((f"{italic_prefix}", consts.UI_NOT_SET))
        else:
            # Normal value display
            if value is not None:
                if value_style:
                    parts.append((value_style, escaped_value))
                else:
                    parts.append(("", escaped_value))  # WHITE - default
            else:
                parts.append(("", consts.UI_NOT_SET))  # DIM - no special color
    
    return parts


def format_variable_detail(key: str, var_spec, current_value, raw_from_file: dict, spec) -> "FormattedText":
    """Format detailed information about a variable for the edit view - compact 3-line format."""
    parts = []
    
    if not key:
        return [(consts.UI_TEXT_DIM, "Select a variable to view details")]  # Could also be a const if needed
    
    # Line 1: Key and docs on same line
    escaped_key = _escape_brackets(key)
    parts.append(("bold", escaped_key))
    docs = var_spec.docs if var_spec and var_spec.docs != consts.DEFAULT_DOCS else None
    if docs:
        escaped_docs = _escape_brackets(docs)
        parts.append((consts.UI_TEXT_DIM, f"  {escaped_docs}"))
    parts.append(("", "\n"))
    
    # Line 2: Type, Current, Default
    var_type = var_spec.type if var_spec else None
    current_str = str(current_value) if current_value is not None else consts.UI_NOT_SET
    default = var_spec.default if var_spec else None
    
    line2_parts = []
    if var_type:
        type_str = var_type.__name__ if isinstance(var_type, type) else str(var_type)
        line2_parts.append(f"type:{type_str}")
    line2_parts.append(f"current:{current_str}")
    if default is not None:
        line2_parts.append(f"default:{default}")
    
    parts.append((consts.UI_TEXT_DIM, "  ".join(line2_parts)))
    parts.append(("", "\n"))
    
    # Line 3: Status, Required, Validated
    key_status = consts.KEY_STATUS_VALID
    has_explicit = spec and spec.has_explicit_spec(key) if spec else False
    if not has_explicit:
        key_status = consts.KEY_STATUS_EXTRA
    elif key not in raw_from_file or raw_from_file.get(key) is None:
        key_status = consts.KEY_STATUS_DEFAULT
    else:
        try:
            if spec:
                try:
                    var_spec_check = spec[key]
                    if var_spec_check.validator:
                        var_spec_check.validator(current_value)
                except KeyError:
                    pass
            key_status = consts.KEY_STATUS_VALID
        except Exception:
            key_status = consts.KEY_STATUS_INVALID
    
    line3_parts = []
    required = var_spec.required if var_spec else False
    if required:
        line3_parts.append("required")
    has_validator = var_spec and var_spec.validator
    if has_validator:
        line3_parts.append("validated")
    if key_status != consts.KEY_STATUS_VALID:
        status_text = {
            consts.KEY_STATUS_DEFAULT: "using-default",
            consts.KEY_STATUS_INVALID: "invalid",
            consts.KEY_STATUS_EXTRA: "extra",
        }.get(key_status, "")
        if status_text:
            line3_parts.append(status_text)
    
    if line3_parts:
        parts.append((consts.UI_TEXT_DIM, "  ".join(line3_parts)))
    
    return parts


def save_env_file(env_data: dict[str, str | None], dst_path: Path, spec_path: Optional[Path] = None):
    """Save environment variables to a file."""
    # Read existing file to preserve comments and structure if it exists
    existing_lines = []
    if dst_path.exists():
        existing_lines = dst_path.read_text().splitlines()
    
    # Build a map of key -> line number in existing file
    key_to_line = {}
    for i, line in enumerate(existing_lines):
        # Match KEY=VALUE pattern (with optional comment)
        # Handle both KEY=VALUE and KEY= formats
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)(?:\s*#.*)?$', line)
        if match:
            key = match.group(1)
            if key not in consts.ENVO_SPECIAL_KEYS:
                key_to_line[key] = i
    
    # Track which keys we've processed
    processed_keys = set()
    
    # Update existing lines
    for key, value in sorted(env_data.items()):
        if key in consts.ENVO_SPECIAL_KEYS:
            continue
        
        processed_keys.add(key)
        value_str = str(value) if value is not None else ""
        
        # Simple quoting - only quote if needed
        needs_quotes = ' ' in value_str or '#' in value_str or not value_str
        if needs_quotes:
            if '"' in value_str:
                value_str = f"'{value_str}'"
            else:
                value_str = f'"{value_str}"'
        
        line_content = f"{key}={value_str}"
        
        if key in key_to_line:
            # Update existing line
            line_num = key_to_line[key]
            # Preserve comment if present
            old_line = existing_lines[line_num]
            comment_match = re.search(r'\s+#\s*(.+)$', old_line)
            if comment_match:
                line_content = f"{line_content}  # {comment_match.group(1)}"
            existing_lines[line_num] = line_content
        else:
            # Add new line at the end
            existing_lines.append(line_content)
    
    # Write back
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text('\n'.join(existing_lines) + '\n')


def run_interactive_config(
    key: Optional[str] = None,
    group: Optional[str] = None,
    grep: Optional[str] = None,
    ignore_case: bool = False,
    all_vars: bool = False,
    env_file: Optional[list[str]] = None,
    spec: Optional[str] = None,
    no_system: bool = False,
    dst: Optional[str] = None,
):
    """Run the interactive configuration editor."""
    
    # Load spec
    spec_obj = None
    spec_path = spec
    if not spec_path:
        default_spec = find_default_spec()
        if default_spec:
            spec_path = str(default_spec)
    
    if spec_path:
        try:
            spec_obj = env_file_to_spec(spec_path)
        except FileNotFoundError:
            subprint(f"BOLD+RED[Error:] Spec file not found: {_escape_brackets(spec_path)}", file=sys.stderr)
            return 1
    
    # Build Env with validation disabled for loading
    loading_spec = None
    if spec_obj:
        from envo.spec_type import VariableSpec, parse_spec_key
        loading_spec = {}
        for k, v in spec_obj.items():
            new_spec = VariableSpec(
                groups=v.groups,
                docs=v.docs,
                type=v.type,
                default=v.default,
                required=v.required,
            )
            loading_spec[k] = new_spec
        loading_spec[parse_spec_key("*")] = VariableSpec()
    
    try:
        env = Env(
            *(env_file or []),
            spec=loading_spec if loading_spec else ("auto" if not spec else spec),
            existing_env_priority="none" if no_system else "highest",
            export_to_environ=False,
        )
    except FileNotFoundError as e:
        subprint(f"BOLD+RED[Error:] {_escape_brackets(str(e))}", file=sys.stderr)
        return 1
    
    # Filter by group if specified
    if group:
        env = env.get_group(group)
        if not env:
            subprint(f"YELLOW[No variables found in group:] MAGENTA[{_escape_brackets(group)}]", file=sys.stderr)
            return 0
    
    # Get keys to show
    if key:
        # Check if key contains wildcards
        if '*' in key or '?' in key:
            import fnmatch
            pattern = fnmatch.translate(key)
            regex = re.compile(pattern)
            keys = [k for k in sorted(env.keys()) if regex.match(k)]
            if not keys:
                subprint(f"YELLOW[No variables matching pattern:] DIM[{_escape_brackets(key)}]", file=sys.stderr)
                return 0
        else:
            keys = [key]
    elif grep:
        pattern = re.compile(grep, re.IGNORECASE if ignore_case else 0)
        keys = [k for k in sorted(env.keys()) if pattern.search(k)]
        if not keys:
            subprint(f"YELLOW[No variables matching:] DIM[{_escape_brackets(grep)}]", file=sys.stderr)
            return 0
    else:
        keys = sorted(env.keys())
    
    # Filter to only explicitly specified keys (not fallback matches) unless --all
    if spec_obj and not all_vars and not key:
        explicit_keys = env.spec.filter_explicit(keys)
        if not explicit_keys and keys:
            subprint(f"DIM[No explicitly specified variables. Use --all to see all {len(keys)} variables.]", file=sys.stderr)
            return 0
        keys = explicit_keys
    
    if not keys:
        subprint("YELLOW[No variables to configure]", file=sys.stderr)
        return 0
    
    # Get raw values from file
    raw_from_file = {}
    if env_file:
        for ef in env_file:
            raw_from_file.update(load_single_env_raw(ef) or {})
    else:
        default_env = find_default_env()
        if default_env:
            raw_from_file = load_single_env_raw(str(default_env)) or {}
    
    # Determine destination file
    if dst:
        dst_path = Path(dst).expanduser()
    else:
        # Default to .env in project root
        from fpr import find_project_root
        root = find_project_root()
        if root:
            dst_path = Path(root) / consts.DEFAULT_ENV_FILE
        else:
            dst_path = Path.cwd() / consts.DEFAULT_ENV_FILE
    
    # Track changes (pending, unsaved)
    changes: dict[str, str | None] = {}
    
    # Track committed values (saved to file, for display after save)
    committed_values: dict[str, str | None] = {}
    
    # Create the interactive application
    # Store app reference for use in callbacks (defined early for get_visible_list_height)
    app_ref = [None]  # Use list to allow modification in nested scope
    
    # Simple state - selected_index ONLY changes in arrow handlers
    state = {
        'selected_index': 0,
        'scroll_offset': 0,  # First visible item index for scrolling
        'edit_mode': False,
        'current_edit_key': None,
        'edit_buffer': None,
        'original_edit_value': None,
        'edit_cleared': False,
        'validation_result': (True, None),  # (is_valid, error_message)
        'validated_value': None,  # The parsed/validated value after coercion
        'cached_layout': None,  # Layout cache
        'cached_edit_mode': None,  # Track edit mode for layout cache
        'text_changed_handler': None,  # Text change handler reference
    }
    
    def get_visible_list_height() -> int:
        """Calculate how many list items can be visible based on terminal height."""
        if app_ref[0] and app_ref[0].output:
            try:
                size = app_ref[0].output.get_size()
                terminal_height = size.rows
                # Subtract space for: header(1) + blank(1) + separator(1) + detail(3) + help(1) + buffer(1)
                list_height = terminal_height - 8
                return max(1, list_height)
            except Exception:
                pass
        # Fallback to reasonable default
        return 20
    
    def ensure_selected_visible():
        """Adjust scroll_offset so selected_index is visible."""
        visible_height = get_visible_list_height()
        selected = state['selected_index']
        scroll = state['scroll_offset']
        
        # If selected is above visible area, scroll up
        if selected < scroll:
            state['scroll_offset'] = selected
        # If selected is below visible area, scroll down
        elif selected >= scroll + visible_height:
            state['scroll_offset'] = selected - visible_height + 1
        
        # Clamp scroll_offset to valid range
        max_scroll = max(0, len(keys) - visible_height)
        state['scroll_offset'] = max(0, min(state['scroll_offset'], max_scroll))
    
    def get_variable_status(key: str) -> str:
        """Determine the status of a variable."""
        has_explicit = spec_obj and spec_obj.has_explicit_spec(key) if spec_obj else False
        if not has_explicit:
            return consts.KEY_STATUS_EXTRA
        elif key not in raw_from_file or raw_from_file.get(key) is None:
            return consts.KEY_STATUS_DEFAULT
        else:
            try:
                value = env.get(key)
                if spec_obj:
                    var_spec_check = spec_obj[key]
                    if var_spec_check.validator:
                        var_spec_check.validator(value)
                return consts.KEY_STATUS_VALID
            except Exception:
                return consts.KEY_STATUS_INVALID
    
    
    # Create UI components with proper state management
    def get_list_content():
        """Get the current list content with scrolling support."""
        content = []
        
        # Calculate visible range
        visible_height = get_visible_list_height()
        scroll_offset = state['scroll_offset']
        start_idx = scroll_offset
        end_idx = min(len(keys), scroll_offset + visible_height)
        
        # Show scroll indicator at top if scrolled down
        if scroll_offset > 0:
            content.append((consts.UI_TEXT_DIM, f"  ↑ {scroll_offset} more above\n"))
        
        for i in range(start_idx, end_idx):
            key = keys[i]
            # Priority: pending changes > committed values > env
            if key in changes:
                value = changes[key]
            elif key in committed_values:
                value = committed_values[key]
            else:
                value = env.get(key)
            status = get_variable_status(key)
            selected = (i == state['selected_index']) and not state['edit_mode']
            has_unsaved = key in changes
            # For strikethrough, show the committed/env value as "saved"
            if has_unsaved:
                saved_value = committed_values.get(key, env.get(key))
            else:
                saved_value = None
            line = format_variable_line(key, value, status, selected, has_unsaved, saved_value)
            content.extend(line)
            content.append(("", "\n"))
        
        # Show scroll indicator at bottom if more items below
        remaining = len(keys) - end_idx
        if remaining > 0:
            content.append((consts.UI_TEXT_DIM, f"  ↓ {remaining} more below"))
        
        return content
    
    def validate_edit_value(text: str) -> tuple[bool, str | None, Any]:
        """Validate the current edit value using the spec - only validates THIS variable.
        
        Returns:
            (is_valid, error_message, validated_value)
        """
        if not state['edit_mode'] or not state['current_edit_key'] or not spec_obj:
            return (True, None, None)
        
        edit_key = state['current_edit_key']
        
        # Get the spec for this variable
        try:
            var_spec = spec_obj[edit_key]
        except KeyError:
            # Variable not in spec, allow any value
            return (True, None, text)
        
        # Infer type from default if type is not set
        effective_type = var_spec.type
        if effective_type is None and var_spec.default is not None and var_spec.default != "":
            # Try to infer type from default value
            from envo.coerce import coerce_unknown
            try:
                coerced_default = coerce_unknown(var_spec.default)
                # Get the type of the coerced value
                if isinstance(coerced_default, bool):
                    effective_type = bool
                elif isinstance(coerced_default, int):
                    effective_type = int
                elif isinstance(coerced_default, float):
                    effective_type = float
                # For strings, paths, dicts, lists - keep as None (no type enforcement)
            except Exception:
                # If coercion fails, leave type as None
                pass
        
        # Empty value - check if required
        if not text.strip():
            if var_spec.required:
                return (False, "Required variable cannot be empty", None)
            return (True, None, None)
        
        # First, check type coercion - ALWAYS enforce spec type (or inferred type) if it exists
        if effective_type is not None:
            try:
                # Resolve references first for type checking
                temp_raw = {}
                for key in keys:
                    if key in env.raw:
                        temp_raw[key] = env.raw[key]
                temp_raw[edit_key] = text
                temp_raw = resolve_var_references(temp_raw)
                resolved_text = temp_raw[edit_key]
                
                # Apply pre-processing if specified
                if var_spec.pre:
                    resolved_text = var_spec.pre(resolved_text)
                
                # Try to coerce to the effective type (spec type or inferred from default)
                if var_spec.coerce is True:
                    # Use built-in coerce function
                    coerced = coerce(resolved_text, effective_type)
                    # Check that the result is actually the expected type
                    # coerce returns None on failure for int/float, so we need to check
                    if effective_type is not None:
                        # For int/float, None means coercion failed
                        if effective_type in (int, float) and coerced is None:
                            raise ValueError(f"Cannot convert '{resolved_text}' to {effective_type.__name__}")
                        # For other types, check if result matches expected type
                        elif effective_type is not str and not isinstance(coerced, effective_type):
                            # Allow None for optional types, but not wrong types
                            if coerced is not None:
                                raise ValueError(f"Cannot convert '{resolved_text}' to {effective_type.__name__}: got {type(coerced).__name__}")
                elif var_spec.coerce:
                    # Use custom coerce function
                    coerced = var_spec.coerce(resolved_text)
                else:
                    # No coercion specified - this shouldn't happen if type is set, but handle it
                    # If type is set but coerce is False, we can't validate type
                    coerced = resolved_text
                
                # Check raw_validator if present
                if var_spec.raw_validator:
                    var_spec.raw_validator(resolved_text)
                
                # Apply post-processing if specified
                if var_spec.post:
                    coerced = var_spec.post(coerced)
                
                # Check validator if present
                if var_spec.validator:
                    var_spec.validator(coerced)
                
                return (True, None, coerced)
            except Exception as e:
                return (False, str(e), None)
        else:
            # No type specified, try full Env validation for reference resolution
            try:
                # Create a temporary Env with only the variable being edited and any referenced variables
                temp_raw = {}
                for key in keys:
                    if key in env.raw:
                        temp_raw[key] = env.raw[key]
                temp_raw[edit_key] = text
                temp_raw = resolve_var_references(temp_raw)
                temp_env = Env(
                    raw=temp_raw, 
                    spec=spec_obj, 
                    existing_env_priority="none", 
                    export_to_environ=False,
                    allow_extra=True
                )
                validated = temp_env[edit_key]
                return (True, None, validated)
            except Exception as e:
                return (False, str(e), None)
    
    def get_detail_content():
        """Get the current detail content."""
        if state['edit_mode'] and state['current_edit_key']:
            key = state['current_edit_key']
        elif keys:
            key = keys[state['selected_index']]
        else:
            return [("dim", "No variables available")]
        
        try:
            var_spec = spec_obj[key] if spec_obj else None
        except KeyError:
            var_spec = None
        
        # In edit mode, use the validated value if available, otherwise use the raw text
        if state['edit_mode'] and key == state['current_edit_key']:
            # Show the validated/parsed value if validation succeeded and we have a value
            if state['validation_result'][0] and state['validated_value'] is not None:
                current_value = state['validated_value']
            else:
                # Show raw text from buffer (even if empty string)
                raw_text = edit_textarea.buffer.text
                current_value = raw_text if raw_text else None
        else:
            # Priority: pending changes > committed values > env
            if key in changes:
                current_value = changes[key]
            elif key in committed_values:
                current_value = committed_values[key]
            else:
                current_value = env.get(key)
        return format_variable_detail(key, var_spec, current_value, raw_from_file, spec_obj)
    
    list_control = FormattedTextControl(get_list_content)
    # Disable mouse scroll - we only want arrow key navigation
    list_window = Window(
        content=list_control,
        always_hide_cursor=True,
        # Disable mouse scrolling
        allow_scroll_beyond_bottom=False,
    )
    
    detail_control = FormattedTextControl(get_detail_content)
    detail_window = Window(content=detail_control, always_hide_cursor=True, wrap_lines=True, height=3)
    
    edit_textarea = TextArea(
        text="",
        multiline=False,
        wrap_lines=False,
    )
    
    
    # Create a custom buffer control that shows old value in gray
    def get_edit_content():
        """Get the edit field content with old value styling."""
        if not state['edit_mode'] or not state['original_edit_value']:
            return edit_textarea.buffer.text
        
        current_text = edit_textarea.buffer.text
        # If text is empty or matches original, show original in gray
        if not state['edit_cleared'] and (current_text == "" or current_text == str(state['original_edit_value'])):
            return str(state['original_edit_value'])
        return current_text
    
    def get_edit_style():
        """Get style for edit field - gray if showing old value."""
        if not state['edit_mode'] or not state['original_edit_value']:
            return ""
        
        current_text = edit_textarea.buffer.text
        if not state['edit_cleared'] and (current_text == "" or current_text == str(state['original_edit_value'])):
            return consts.UI_TEXT_DIM
        return ""
    
    # Use TextArea directly - it handles cursor positioning correctly
    # We'll handle the placeholder styling differently
    
    # Layout - clean single column
    # Cache the layout to prevent unnecessary recreation
    def _get_layout_internal():
        # Only recreate layout if edit_mode changed
        # This prevents the layout from being recreated on every invalidate()
        current_edit_mode = state.get('edit_mode', False)
        if state['cached_layout'] is None or state['cached_edit_mode'] != current_edit_mode:
            state['cached_edit_mode'] = state['edit_mode']
            if state['edit_mode']:
                # TextArea is a container itself, use it directly in the layout
                # No need to wrap it in a Window
                # Header with variable name
                if state['current_edit_key']:
                    escaped_key = _escape_brackets(state['current_edit_key'])
                    header_text = f"Edit Variable: {escaped_key}"
                else:
                    header_text = "Edit Variable"
                
                # Validation status window
                def get_validation_status():
                    if not state['edit_mode']:
                        return [(consts.UI_TEXT_DIM, "")]
                    is_valid, error_msg = state['validation_result']
                    validated_val = state['validated_value']
                    if is_valid and validated_val is not None:
                        # Show the validated value
                        validated_str = _escape_brackets(str(validated_val))
                        return [(consts.VALUE_COLOR_GREEN, f"{consts.UI_VALID_PREFIX} ({validated_str})")]
                    elif is_valid:
                        # Valid but no value (empty or None)
                        return [(consts.VALUE_COLOR_GREEN, consts.UI_VALID_PREFIX)]
                    else:
                        error_text = _escape_brackets(error_msg or "Invalid")
                        return [(consts.VALUE_COLOR_RED, f"{consts.UI_INVALID_PREFIX}: {error_text}")]
                
                validation_window = Window(
                    height=1,
                    content=FormattedTextControl(get_validation_status),
                )
                
                state['cached_layout'] = Layout(
                    HSplit([
                        Window(height=1, content=FormattedTextControl(lambda: [("bold", header_text)])),
                        Window(height=1),
                        detail_window,
                        Window(height=1),
                        edit_textarea,  # TextArea is a container, use directly
                        validation_window,
                        Window(height=1),
                        Window(height=1, content=FormattedTextControl(lambda: [(consts.UI_TEXT_DIM, consts.UI_HELP_EDIT)])),
                    ]),
                    focused_element=edit_textarea,
                )
            else:
                header_text = f"Configure Variables ({len(keys)} variables)"
                state['cached_layout'] = Layout(
                    HSplit([
                        Window(height=1, content=FormattedTextControl(lambda: [("bold", header_text)])),
                        Window(height=1),
                        list_window,
                        Window(height=1, content=FormattedTextControl(lambda: [(consts.UI_TEXT_DIM, consts.UI_SEPARATOR_CHAR * consts.UI_SEPARATOR_WIDTH)])),
                        detail_window,
                        Window(height=1, content=FormattedTextControl(lambda: [(consts.UI_TEXT_DIM, consts.UI_HELP_BROWSE)])),
                    ]),
                    focused_element=list_window,
                )
        return state['cached_layout']
    
    # Simple wrapper
    def get_layout():
        """Get layout."""
        return _get_layout_internal()
    
    # Key bindings - create empty and only add what we need
    kb = KeyBindings()
    
    # Navigation key bindings - only active when not in edit mode
    # Use a Condition that checks state dynamically
    is_not_edit_mode = Condition(lambda: not state['edit_mode'])
    
    # Block mouse scroll events - requires mouse_support=True to receive these
    # instead of the terminal converting them to arrow keys
    
    @kb.add(Keys.ScrollUp)
    def block_scroll_up(event):
        """Consume scroll up events - do nothing."""
        pass
    
    @kb.add(Keys.ScrollDown)
    def block_scroll_down(event):
        """Consume scroll down events - do nothing."""
        pass
    
    @kb.add(Keys.Vt100MouseEvent)
    def block_mouse_event(event):
        """Consume all other mouse events - do nothing."""
        pass
    
    def _navigate_up():
        """Move selection up."""
        state['selected_index'] = max(0, state['selected_index'] - 1)
        ensure_selected_visible()
    
    def _navigate_down():
        """Move selection down."""
        state['selected_index'] = min(len(keys) - 1, state['selected_index'] + 1)
        ensure_selected_visible()
    
    # Arrow key navigation
    @kb.add('up', filter=is_not_edit_mode)
    def go_up(event):
        """Move selection up."""
        _navigate_up()
        event.app.invalidate()
    
    @kb.add('down', filter=is_not_edit_mode)
    def go_down(event):
        """Move selection down."""
        _navigate_down()
        event.app.invalidate()

    
    @kb.add('enter')
    def enter_edit(event):
        if not state['edit_mode']:
            # Ensure handler is detached before entering edit mode
            ensure_handler_detached()
            state['edit_mode'] = True
            state['edit_cleared'] = False
            state['current_edit_key'] = keys[state['selected_index']]
            current_value = changes.get(state['current_edit_key'], env.get(state['current_edit_key']))
            state['original_edit_value'] = current_value
            # Initialize buffer with original value so cursor position matches
            original_text = str(current_value) if current_value is not None else ""
            edit_textarea.text = original_text
            # Move cursor to end - do this after setting text
            edit_textarea.buffer.cursor_position = len(original_text)
            # Validate initial value
            is_valid, error_msg, validated_val = validate_edit_value(original_text)
            state['validation_result'] = (is_valid, error_msg)
            state['validated_value'] = validated_val
            # Attach text change handler for validation
            state['text_changed_handler'] = create_text_changed_handler()
            edit_textarea.buffer.on_text_changed += state['text_changed_handler']
            # Invalidate to ensure cursor is rendered correctly
            event.app.invalidate()
            event.app.layout = get_layout()
        else:
            # Save the edit
            new_value = edit_textarea.text.strip()
            # If user didn't type anything or cleared it, use original
            if not state['edit_cleared'] and (new_value == "" or new_value == str(state['original_edit_value'])):
                new_value = state['original_edit_value']
            if new_value == "":
                new_value = None
            changes[state['current_edit_key']] = new_value
            # Remove text change handler to prevent interference
            if state['text_changed_handler']:
                edit_textarea.buffer.on_text_changed -= state['text_changed_handler']
                state['text_changed_handler'] = None
            state['edit_mode'] = False
            state['current_edit_key'] = None
            state['original_edit_value'] = None
            state['edit_cleared'] = False
            event.app.layout = get_layout()
    
    @kb.add('c-c')
    def cancel_edit(event):
        if state['edit_mode']:
            # Remove text change handler to prevent interference
            if state['text_changed_handler']:
                edit_textarea.buffer.on_text_changed -= state['text_changed_handler']
                state['text_changed_handler'] = None
            state['edit_mode'] = False
            state['current_edit_key'] = None
            state['original_edit_value'] = None
            state['edit_cleared'] = False
            state['validation_result'] = (True, None)
            state['validated_value'] = None
            event.app.layout = get_layout()
        else:
            event.app.exit()
    
    # Ensure handler is detached at startup and whenever we exit edit mode
    def ensure_handler_detached():
        """Ensure the text change handler is detached."""
        if state['text_changed_handler']:
            try:
                edit_textarea.buffer.on_text_changed -= state['text_changed_handler']
            except (ValueError, AttributeError):
                pass
            state['text_changed_handler'] = None
    
    # Call it once to ensure clean state
    ensure_handler_detached()
    
    # Track if we're currently processing navigation to prevent interference
    _navigating = False
    
    def create_text_changed_handler():
        """Create the text changed handler function."""
        def on_text_changed(buffer):
            """Called AFTER text in edit buffer changes."""
            # ONLY process if in edit mode
            if not state.get('edit_mode', False):
                return
            if not state.get('current_edit_key'):
                return
            if not app_ref[0]:
                return
            # Update validation
            text = buffer.text
            original_str = str(state['original_edit_value']) if state['original_edit_value'] is not None else ""
            if text != original_str:
                state['edit_cleared'] = True
            try:
                is_valid, error_msg, validated_val = validate_edit_value(text)
                state['validation_result'] = (is_valid, error_msg)
                state['validated_value'] = validated_val
            except Exception:
                state['validation_result'] = (False, "Validation error")
                state['validated_value'] = None
            # Invalidate to update display
            if app_ref[0]:
                app_ref[0].invalidate()
        return on_text_changed
    
    # Track saved changes for display after exit
    saved_changes: dict[str, tuple] = {}  # key -> (old_value, new_value)
    
    # Track save errors to display
    save_error: list[str] = []
    
    def save_changes(event):
        if not state['edit_mode']:
            # Save only changed variables to file
            if changes:
                # Only include changed keys and keys already in file
                env_data = {}
                for key in raw_from_file:
                    if key in changes:
                        env_data[key] = changes[key]
                    else:
                        env_data[key] = raw_from_file[key]
                # Add any changed keys not already in file
                for key in changes:
                    if key not in env_data:
                        env_data[key] = changes[key]
                
                try:
                    save_env_file(env_data, dst_path, Path(spec_path) if spec_path else None)
                    # Store saved changes for display after exit
                    for key, new_val in changes.items():
                        old_val = committed_values.get(key, env.get(key))
                        saved_changes[key] = (old_val, new_val)
                        # Update raw_from_file so subsequent saves know this is now in file
                        raw_from_file[key] = str(new_val) if new_val is not None else ""
                        # Update committed_values so the display shows the new value
                        committed_values[key] = new_val
                    changes.clear()
                    # Stay in TUI, don't exit
                    event.app.invalidate()
                except Exception as e:
                    save_error.clear()
                    save_error.append(str(e))
                    event.app.invalidate()
    
    @kb.add('c-s')
    def save_changes_ctrl_s(event):
        save_changes(event)
    
    @kb.add('c-o')
    def save_changes_ctrl_o(event):
        save_changes(event)
    
    def quit_app(event):
        if not state['edit_mode']:
            event.app.exit()
    
    @kb.add('c-q')
    def quit_app_ctrl_q(event):
        quit_app(event)
    
    @kb.add('c-x')
    def quit_app_ctrl_x(event):
        quit_app(event)
    
    # Create and run application
    app = Application(
        layout=get_layout(),
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
        enable_page_navigation_bindings=False,
    )
    
    # Store app reference for validation callback
    app_ref[0] = app

    # Function to clear TUI output and show saved changes
    def clear_and_show_saved():
        # Move cursor up to clear TUI output - use ED (Erase in Display) to clear from cursor to end
        # First, count approximate lines used by TUI (header + blank + list + separator + blank + detail + blank + footer)
        tui_lines = 2 + len(keys) + 1 + 3 + 1  # header + blank + list + separator + detail + help
        # Move up and clear each line
        sys.stdout.write(f"\x1b[{tui_lines}A")  # Move cursor up
        sys.stdout.write("\x1b[J")  # Clear from cursor to end of screen
        sys.stdout.flush()
        
        # Show saved changes if any
        if saved_changes:
            subprint(f"BOLD+GREEN[Saved to {_escape_brackets(str(dst_path))}:]")
            for key, (old_val, new_val) in sorted(saved_changes.items()):
                old_str = str(old_val) if old_val is not None else "(not set)"
                new_str = str(new_val) if new_val is not None else "(not set)"
                subprint(f"  CYAN[{_escape_brackets(key)}] = DIM[{_escape_brackets(old_str)}] → GREEN[{_escape_brackets(new_str)}]")
    
    result = None
    error_result = None
    
    try:
        result = app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        error_result = str(e)
    
    # Clear TUI output on any exit
    clear_and_show_saved()
    
    # Handle results after clearing
    if error_result:
        subprint(f"BOLD+RED[Error:] {_escape_brackets(error_result)}", file=sys.stderr)
        return 1
    
    if result and result.startswith("error:"):
        error_msg = result.split(":", 1)[1]
        subprint(f"BOLD+RED[Error saving file:] {_escape_brackets(error_msg)}", file=sys.stderr)
        return 1

    # Save on exit if there are unsaved changes
    if changes:
        try:
            response = input(f"Save {len(changes)} change(s) to {dst_path}? [y/N]: ")
        except KeyboardInterrupt:
            print()  # New line after ^C
            return 0
        if response.lower() == 'y':
            # Only include changed keys and keys already in file
            env_data = {}
            for key in raw_from_file:
                if key in changes:
                    env_data[key] = changes[key]
                else:
                    env_data[key] = raw_from_file[key]
            # Add any changed keys not already in file
            for key in changes:
                if key not in env_data:
                    env_data[key] = changes[key]
            
            try:
                save_env_file(env_data, dst_path, Path(spec_path) if spec_path else None)
                # Store and display saved changes
                for key, new_val in changes.items():
                    old_val = env.get(key)
                    saved_changes[key] = (old_val, new_val)
                # Display saved changes
                subprint(f"BOLD+GREEN[Saved to {_escape_brackets(str(dst_path))}:]")
                for key, (old_val, new_val) in sorted(saved_changes.items()):
                    old_str = str(old_val) if old_val is not None else "(not set)"
                    new_str = str(new_val) if new_val is not None else "(not set)"
                    subprint(f"  CYAN[{_escape_brackets(key)}] = DIM[{_escape_brackets(old_str)}] → GREEN[{_escape_brackets(new_str)}]")
            except Exception as e:
                subprint(f"BOLD+RED[Error saving file:] {_escape_brackets(str(e))}", file=sys.stderr)
                return 1
    
    return 0

