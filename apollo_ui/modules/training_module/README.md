# Apollo Training Module 2.0

This replaces the broken placeholder module.

## Apollo tools

- `training_module.search_web`
- `training_module.fetch_page`
- `training_module.save_to_file`
- `training_module.read_from_file`
- `training_module.list_research_files`
- `training_module.explore_web_and_save`

## Local storage

Runtime research is stored under:

`Apollo/storage/training_module/`

The module cannot use `../` or absolute paths to escape that folder.

## UI

This module supports Apollo V6.6's dynamic module UI system.

Its default placement is:

`Apps -> Research & Training`

You can change it from:

`Modules -> Training Module -> Selected Module UI`

to:

- Hidden / Tool Only
- Apps Page
- Sidebar Tab

## Validation

The validator tests do not require live internet access. Web search is mocked for
the research-and-save test, while file storage, API structure and path safety are
tested normally.
