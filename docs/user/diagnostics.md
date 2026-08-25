# Configure zppy Diagnostics for SimBoard

zppy publishes diagnostics web output; SimBoard links that output to an existing SimBoard case. The resulting link lets people open the diagnostics directly from the case.

## Configure zppy for SimBoard

In zppy configuration, enable SimBoard with `[simboard] enabled = True`. Set `simulation_type` to `production` or `development`; it defaults to `development`. `none` cannot be used while SimBoard is enabled. When no `www` path is provided, zppy uses the Mache web-portal configuration to infer it; you can also provide an explicit override. See the [zppy SimBoard configuration guide](https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/ac.forsyth2/zppy_docs_pr841_20260730/html/user_guide/tasks/simboard.html) for the exact configuration.

To promote diagnostics from `development` to `production`, follow zppy's manual move/copy process. Do not treat promotion as a SimBoard link update.

## Before you publish

1. Confirm that the intended case is already visible in SimBoard.
2. Check that provenance `case_name`, `machine`, and `hpc_username` match that case.
3. Apply the **SimBoard archive layout rule**:
   - ungrouped output must be at `simulation_type/case`;
   - grouped output must be at `simulation_type/case_group/case`, using the `CASE_GROUP` parameter in E3SM run script configurations. This is not a zppy configuration option. The layout and its values must agree with the provenance, or discovery will not find the output.

If the case is not available in SimBoard, contact the SimBoard administrator: [Tom Vo](mailto:vo13@llnl.gov).

## Publish and find the link

1. Run and publish the zppy diagnostics using the configured `simulation_type`. This generates timestamped paired provenance files: `provenance.*.cfg` and its corresponding `provenance.*.settings`, which SimBoard uses for publication.
2. Confirm that the diagnostics web output is complete and opens successfully in a browser.
3. Confirm the completed public output uses the matching SimBoard archive layout.
4. Wait for the scheduled SimBoard scanner to attempt linkage. Linking is not immediate; the scanner runs periodically.
5. After the link appears, open the case in SimBoard and follow its diagnostics link.

Discovery uses the latest valid provenance for each published diagnostics case. If current provenance is incomplete or invalid, re-run and re-publish zppy diagnostics to regenerate it, then run discovery again. Do not manually edit provenance files or expect discovery to use an older provenance file.

## URL behavior

The initial external URL is stable for a published case path. When content is updated at that same published path, the SimBoard link continues to use that URL.

If output is deleted or moved, restore it at the original URL to keep the link working. Otherwise, manually update or remove the link in SimBoard. SimBoard does not dynamically check or remove existing links whose external output is unavailable.

## Troubleshooting

**The case does not receive a diagnostics link.** Check the configured `simulation_type`, the matching grouped or ungrouped archive layout, the latest provenance and paired settings, the required case identity, and that the completed output is publicly accessible. If it is still missing, contact [Tom Vo](mailto:vo13@llnl.gov).

**The link opens the wrong output.** Check `simulation_type`, `case_group`, and the published path. SimBoard does not semantically validate whether the selected `simulation_type` is appropriate for the output.

**The link no longer opens.** Restore the output at its original URL, or manually update or remove the SimBoard link.

For SimBoard scanner implementation details, see [Diagnostics Linkage Architecture](../architecture/diagnostics-linkage.md).
