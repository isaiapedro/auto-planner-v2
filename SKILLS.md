# PIOS v2 Command System & Slash Workflows

This document establishes the precise operational loops for the system using the underlying MCP architecture.

## /capture
**Trigger:** User uploads a raw recording transcript, log, or quick brainstorm note.
1. **Intake Processing:** Read file inside the immutable `/raw` collection.
2. **Local Extraction:** Trigger local Ollama parser to isolate key entities, relevant personalized domains (e.g., Technology, Art, Literature), and active projects.
3. **Graph Storage:** Execute PostgreSQL MCP statements to insert raw properties into the relational Evidence Graph.
4. **Wiki Sync:** Append a clean markdown reference page into `/wiki/sources/`. Cross-link relevant nodes within `/wiki/entities/` and `/wiki/concepts/` using explicit `[[wikilinks]]`. Append the proper `^[extracted]` provenance tag.
5. **Logging:** Add entry to `/wiki/log.md` with prefix format: `## [YYYY-MM-DD] capture | [Source Identifier]`.

## /reflect
**Trigger:** Executed to resolve data inconsistencies or run deep contextual cross-referencing.
1. **Vault Structural Scan:** Parse `/wiki/concepts/` and recent entries inside `/wiki/syntheses/`.
2. **Contradiction Detection:** Locate semantic anomalies where new inputs conflict with existing historical files.
3. **Tag Anomalies:** Convert unresolved conflicts into explicit `^[ambiguous]` tags and surface them to the user.
4. **Archive Discovery:** Consolidate validated thematic relationships into a new file inside `/wiki/syntheses/`, updating `/wiki/index.md`.

## /weekly-review
**Trigger:** User runs or schedules an automated end-of-week assessment.
1. **Metric Aggregation:** Execute SQL queries via the PostgreSQL MCP to read from the Feature Registry tables (e.g., tracking Focus Quality, Domain Balance, and Learning Velocity over the preceding 7 days).
2. **Context Assembly:** Read the past 7 days of entries from `/wiki/log.md`.
3. **Synthesis Generation:** Leverage a frontier Claude model to contrast target domain commitments against historical performance data.
4. **Output Generation:** Write a structured markdown analysis directly to `/wiki/audits/weekly_review_[YYYY_WW].md`. Identify core operational bottlenecks and list open questions.

## /monthly-review
**Trigger:** Strategic evaluation run at the completion of a calendar month.
1. **Long-Term Retrieval:** Extract the 4 previous weekly reviews alongside calculated monthly aggregates from the database.
2. **Identity Drift Analysis:** Compute embedding trajectories over the month's narrative inputs to measure shifting thematic focus.
3. **Structural Overhaul:** Suggest adjustments to the primary allocations of the Exploration Domains (e.g., shifting percentage weight from Technology to Craftsmanship based on verified engagement).
4. **File Generation:** Save the final long-term strategy dossier into `/wiki/audits/monthly_review_[YYYY_MM].md`.

## /dashboard
**Trigger:** Request to view current state metrics.
1. **Refresh Views:** Run database queries to rebuild denormalized materialized views across all primary behavioral features.
2. **Layout Presentation:** Construct a clean markdown table summarizing current data indicators:
    * Domain Balance (Target Hours vs Verifiable Executed Hours)
    * Knowledge Base Growth Rate (New pages, interlink count, unlinked orphan count)
    * System Bottlenecks (Active `^[ambiguous]` tokens requiring review)
3. **LLM Restraint:** Do not write speculative prose; display the exact calculated database values.

## /plan
**Trigger:** User seeks calendar recommendations for the upcoming weekly period.
1. **Resource Mapping:** Query the Google Calendar MCP to isolate all immutable Fixed Blocks (appointments, predetermined meetings) for the next 7 days.
2. **Capacity Computation:** Compute remaining time windows. Map these windows into pure Exploration Blocks.
3. **Prioritization Layer:** Match current high-priority open questions or active projects against the personalized domains.
4. **Draft Allocation:** Propose a structural calendar layout schema distributing the available Exploration Blocks across domains (e.g., Morning: Technology/PIOS, Evening: Literature/Writing).
5. **Calendar Dispatch:** Upon user approval, push the scheduled blocks to the host system using the Google Calendar automation engine.

## /research-map
**Trigger:** Initiated when deep-diving a complex technical landscape or conceptual web.
1. **Indexing Pass:** Scan the core knowledge indexes and vector storage paths for the target topic.
2. **Lineage Synthesis:** Map the developmental tree of the concept, identifying its foundational references, active projects drawing from it, and connected external read-only code or reference documentation.
3. **Visual Structure Generation:** Output a comprehensive markdown file mapping the concept hierarchy using clear nested lists, cross-linked nodes, and directional dependency indicators. File the output inside `/wiki/syntheses/`.
