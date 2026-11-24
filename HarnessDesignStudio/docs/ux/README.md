# Pictures of the editor

| Folder | What is in it | Made by |
| --- | --- | --- |
| [`qt/`](qt/) | 32 pictures of the real editor, offscreen, 1440 x 900, light theme: the built-in sample (01 to 13) and the views and dialogs of the redesigned editor on the flatsat example (14 to 32; 27 and 28 are the Settings sections of the harness plans, 3.0.0; 29 and 30 the pin rows of a connector, 4.0.0; 31 the Devices tab with a pin current and a checked device and 32 the window *Change group* with where the shield ends land, 5.0.0). These are the current pictures. | `python -m tools.gui_screenshots` |
| [`../img/`](../img/) | The flatsat diagram (overview and one unit in focus) used by the README and [`../FLATSAT_EXAMPLE.md`](../FLATSAT_EXAMPLE.md). | `python -m tools.flatsat_screenshots` |
| [`build/`](build/) | Before and after pictures taken by each branch of the UX redesign (canvas, state marks, project tree, checks), light and dark, at 1280 x 720 and 1920 x 1080. History of the work; they are not refreshed. | by hand, per branch |
| [`custom-devices/`](custom-devices/) | 12 pictures of the real editor on the flatsat example (offscreen, light theme) that the custom-devices audit [`../ux-custom-devices-audit.md`](../ux-custom-devices-audit.md) refers to: what the editor offers today for a device of your own. They are not refreshed. | a throwaway script with `widget.grab()` |
| [`audit/`](audit/) | The pictures the audit [`../ux-audit.md`](../ux-audit.md) refers to: the editor before the redesign. They are not refreshed. | by hand |
| [`screens/`](screens/) | Pictures of the clickable HTML prototype that came before the editor ([`screens/README.md`](screens/README.md)). History. | `python -m tools.ux_screenshots` (needs Playwright) |

The design rules behind the pictures are in [`../DESIGN.md`](../DESIGN.md).

## Feedback records

| Record | What is in it |
| --- | --- |
| [`feedback-2026-11-16.md`](feedback-2026-11-16.md) | The feedback of two demo participants on 2.0.0 (a systems engineer, and an electrical engineer and AIT), without names, with a table of each point: covered today, gap, planned release. |

