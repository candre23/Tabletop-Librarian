# Tabletop Librarian User Guide

This manual describes the day-to-day operation of **Tabletop Librarian (TTL) 1.0.0**. It is intended for both Game Masters who administer a TTL server and players who use it to read books, search rules, ask the rules assistant, and manage characters.

For installation, upgrades, service management, and release-platform requirements, see [Installation](INSTALLATION.md). For the optional standalone llama.cpp manager, see [TTL Local AI Backend](AI_BACKEND.md). For System Pack authoring, see [System Packs](SYSTEM_PACKS.md).

---

## Contents

1. [What Tabletop Librarian does](#what-tabletop-librarian-does)
2. [First connection and initial setup](#first-connection-and-initial-setup)
3. [Accounts, roles, and permissions](#accounts-roles-and-permissions)
4. [Navigation and the Settings & About dialog](#navigation-and-the-settings--about-dialog)
5. [Bookshelf and virtual folders](#bookshelf-and-virtual-folders)
6. [Library administration](#library-administration)
7. [Uploads](#uploads)
8. [Document readers](#document-readers)
9. [Search](#search)
10. [Knowledgebase administration](#knowledgebase-administration)
11. [OCR](#ocr)
12. [Semantic embeddings and hybrid retrieval](#semantic-embeddings-and-hybrid-retrieval)
13. [AI provider settings](#ai-provider-settings)
14. [Ask Tabletop Librarian](#ask-tabletop-librarian)
15. [Play Workspace](#play-workspace)
16. [Characters](#characters)
17. [Character creation](#character-creation)
18. [Playing and configuring a character](#playing-and-configuring-a-character)
19. [Temporary modifiers](#temporary-modifiers)
20. [Character advancement](#character-advancement)
21. [Character import and export](#character-import-and-export)
22. [System Packs](#system-packs)
23. [Built-in Generic D20](#built-in-generic-d20)
24. [The bundled D20 SRD bookshelf folder](#the-bundled-d20-srd-bookshelf-folder)
25. [Recommended operating workflow](#recommended-operating-workflow)
26. [What TTL stores and what it does not modify](#what-ttl-stores-and-what-it-does-not-modify)
27. [Common questions](#common-questions)

---

# What Tabletop Librarian does

Tabletop Librarian combines several related tabletop-RPG tools in one self-hosted web application:

- a bookshelf for PDFs, comics, images, text, and Markdown documents;
- virtual folders that organize physical files without requiring the source files to be moved;
- per-folder and per-document player visibility;
- browser-based readers;
- full-text search;
- OCR for scanned PDFs and image-based comic archives;
- a staged searchable knowledgebase;
- lexical and semantic retrieval;
- an optional AI rules assistant;
- character creation and play through installable System Packs;
- portable character and System Pack packages;
- a combined rules/book/character workspace.

TTL is designed so the original game-library files can remain read-only. Generated covers, OCR derivatives, extracted text, embeddings, characters, account data, and configuration are stored separately in TTL's writable data/cache locations.

AI is optional. The bookshelf, readers, accounts, search, OCR, System Packs, and characters do not require a configured LLM.

---

# First connection and initial setup

A newly installed server redirects the first browser connection to the setup page.

## Create the initial GM account

The setup page asks for:

- **Username**
- **Password**
- **Confirm password**

The first account is always the initial GM administrator.

Usernames:

- are required;
- may be up to 64 characters.

Passwords must be at least 8 characters.

After setup completes, TTL signs the initial GM in and prevents the initial-setup workflow from being run again.

## Fresh-install bookshelf

A clean TTL 1.0 installation includes a preconfigured virtual folder named **D20 SRD**. It contains the bundled SRD 5.2.1 PDF and uses the included project-created cover artwork.

This folder is seeded only when a library has never been initialized. TTL does not recreate it simply because it is missing. Therefore, if the GM later deletes or reorganizes it, that choice remains persistent.

---

# Accounts, roles, and permissions

TTL has two account roles:

- **GM**
- **Player**

## GM accounts

A GM can:

- see all library folders and documents;
- administer virtual folders and physical sources;
- set folder and document visibility;
- upload and assign custom document covers;
- administer OCR and the knowledgebase;
- configure semantic embeddings;
- configure and test AI providers;
- create, disable, re-enable, reset, and delete user accounts;
- install or replace System Packs;
- see player characters;
- open player characters directly;
- import a character for a selected user.

The last enabled GM account cannot be disabled, preventing accidental lockout of all administrators.

## Player accounts

A player can:

- browse folders and documents that are visible to players;
- read those documents;
- use Search against indexed documents they are allowed to see;
- upload supported documents into their own upload staging area;
- use Ask within their permitted library scope;
- use their own characters;
- create characters with installed System Packs;
- export/import their own characters.

Players do not receive Library, Users, or Knowledgebase administration controls.

## Visibility is enforced beyond the bookshelf

Player visibility is not merely a display filter. It is also applied when TTL builds a user's available search and AI-retrieval scope. A document marked GM-only should therefore not become accessible to a player through Search or Ask.

## User administration

GMs manage accounts from **Users** in the main navigation.

For each account, the GM can:

- enable or disable it;
- set a new password;
- delete the account.

The page also contains **Add Player**, which creates a new player account.

Disabling an account prevents normal authentication without deleting its saved data.

There is no player-facing self-service password-change screen in TTL 1.0. A GM resets passwords through Users.

---

# Navigation and the Settings & About dialog

Once logged in, the primary navigation contains:

- **Bookshelf**
- **Characters**
- **Search**
- **Uploads**

A GM additionally sees:

- **Knowledgebase**
- **Users**
- **Library**

The current username appears at the right. GM accounts are identified with `(GM)`.

## TTL button

The **TTL** button at the left of the navigation opens **Settings & About**.

In TTL 1.0 this dialog provides:

- application name;
- installed version;
- a short description;
- the project GitHub link.

Operational settings are located in the feature-specific administration pages rather than this dialog. For example, AI and embedding settings are under Knowledgebase, and library settings are under Library.

## Log Out

**Log Out** clears the current web session and returns the user to the authentication flow.

---

# Bookshelf and virtual folders

The Bookshelf is TTL's normal home page.

A **virtual folder** is a logical collection in TTL. It does not need to correspond one-to-one with a physical directory. A virtual folder can contain one or more physical directory/file sources.

Examples:

- `Shadowrun`
- `Pathfinder`
- `Campaign - Tuesday`
- `D20 SRD`

Folder cards display a configured folder cover when one is available.

Selecting a folder opens its document grid.

## Folder document grid

Each visible document is shown with:

- cover art or a format placeholder;
- display name;
- file type.

Select a document to open the appropriate reader.

## Ask this folder

A folder page includes **Ask this folder**. It opens Ask in an embedded panel with retrieval restricted to that virtual folder.

The player can still further limit the question to specific documents inside that folder.

## Unavailable source warning

If one or more configured physical sources are unavailable, a GM sees a warning on the folder page.

TTL deliberately distinguishes an unavailable/offline source from a confirmed deletion where possible. This is important for libraries on removable media or network shares: a temporary outage should not automatically be interpreted as deletion of the library contents.

---

# Library administration

GMs use **Library** to create virtual folders, connect physical sources, manage visibility, choose folder covers, and manage document-specific cover artwork.

## Create Virtual Folder

Enter a folder name and choose its default visibility:

- **Players and GM**
- **GM only**

Then select **Create Folder**.

A virtual folder name cannot contain `/` or `\`.

Creating a virtual folder does not create or move any source game files.

## Delete Folder

**Delete Folder** removes the virtual folder definition from TTL.

It does **not** delete the physical source files.

The folder's source relationships and TTL metadata are removed, but the original game-library files remain where they were.

## Folder visibility

Each folder has a visibility selector:

### Players and GM

The folder is normally visible to both roles.

### GM only

The folder is hidden from players by default.

Document-level visibility overrides can supersede the folder default.

Select **Update** to save the folder visibility.

## Default folder cover

The **Default folder cover** selector allows the GM to choose a document within that virtual folder as the document whose cover represents the folder.

The folder cover therefore consists of two decisions:

1. which document represents the folder;
2. which artwork TTL uses for that document.

If that chosen document has a manual cover, the folder naturally uses that manual artwork.

This is how the bundled **D20 SRD** folder uses the project-created SRD artwork: the SRD PDF is the folder-cover document and that PDF has a manual cover.

## Physical Sources

A virtual folder can contain multiple source entries.

TTL supports:

- a physical directory;
- an individual supported file;
- an uploaded file that a GM assigns as a source.

### Add Physical Source

Enter the full path to a file or directory on the server and select **Add Physical Source**.

The path must be accessible from the machine running TTL. A path visible only on the user's browser computer is not sufficient unless that same path is mounted on the TTL server.

When a directory is added, TTL registers that directory **and each descendant directory as an independent source**. This allows a large directory tree to be imported at once while still allowing individual subfolders to be removed later.

Large source trees can take time to scan. TTL displays a scan-progress overlay and asks the administrator to keep the page open until the operation completes.

### Remove source

**Remove** disconnects that source from the virtual folder.

It does not delete the physical directory or file.

### Read-only sources

A source does not need to be writable. TTL's generated files are kept separately, so a mounted read-only NAS share is a supported library model.

## Supported document formats

TTL 1.0 recognizes:

- `.pdf`
- `.cbz`
- `.cbr`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`
- `.gif`
- `.txt`
- `.md`

Unsupported files are ignored during normal library scans.

## Documents and per-file visibility

Each discovered document has a visibility selector with:

- **Inherit folder**
- **Players and GM**
- **GM only**

### Inherit folder

Uses the containing virtual folder's visibility setting.

### Players and GM

Explicitly makes that document player-visible even if the folder default is GM-only.

### GM only

Explicitly hides that document from players even if the folder default is player-visible.

This permits mixed folders, such as a game system folder that contains both player rules and GM-only adventures.

## Document cover controls

Each document has a **Cover** control.

### Upload Cover

Upload one of:

- PNG
- JPG/JPEG
- WebP

TTL converts and stores this as its manual cover for that document.

The original source document is not modified.

### Restore Automatic

Deletes the manual cover override. TTL returns to the cover automatically generated from the document itself.

For PDFs, that usually means a rendered first page. Comic/image readers similarly derive an automatic cover from their source.

## OCR status in Library

Scanned PDFs and comic archives may display:

- **OCR required**
- **OCR complete**

Actual OCR processing is managed from Knowledgebase.

## Unavailable sources

Library displays any source paths that are configured but presently unavailable.

For removable/network sources, correct the mount/network problem before removing the source unless the source was intentionally deleted.

---

# Uploads

The Uploads page is a staging area for files copied into TTL's own writable storage.

## Upload a document

Any logged-in user can upload a supported file.

TTL:

- sanitizes the uploaded filename;
- stores it beneath that user's upload area;
- automatically chooses a unique name if the same filename already exists.

An upload does not automatically appear on the Bookshelf.

## Player view

Players see their own staged uploads.

They cannot assign the uploads into virtual library folders themselves.

## GM view

A GM can see the staged uploads and can:

- select a virtual folder;
- **Add to Folder**;
- delete an unassigned staged upload.

When **Add to Folder** is used, TTL registers that uploaded file as a normal file source of the chosen virtual folder.

## Deleting uploads

A staged upload cannot be deleted from Uploads while it is still assigned as a library source. This prevents the GM from silently breaking an active folder source.

To remove such a file:

1. remove its source relationship in Library;
2. return to Uploads;
3. delete the staged upload.

Unlike removing a physical-source relationship, deleting a staged upload actually deletes the file from TTL's upload storage.

---

# Document readers

TTL selects a reader according to file type.

## PDF reader

The PDF reader embeds the browser's PDF-viewing facility.

Use the normal PDF controls for:

- page navigation;
- zoom;
- browser/PDF search;
- print/download functions exposed by the browser's PDF viewer.

TTL can open a search or AI source directly at a page number.

### Workspace

**Workspace** opens the selected PDF alongside a character and Ask interface.

### Ask this file

**Ask this file** opens a split panel and locks Ask to that document.

When an answer cites a page in the current PDF, selecting the source can jump the PDF pane to the cited page.

## CBZ and CBR comic reader

The comic reader provides:

- **Previous**
- **Next**
- direct page-number entry;
- page count;
- **Fit width**
- **Fit page**
- **Actual size**

Keyboard shortcuts:

- Left Arrow: previous page
- Right Arrow: next page

CBZ is read directly as a ZIP-style comic archive.

CBR requires RAR-capable extraction support. The packaged Windows Server supplies its private CBR extraction runtime; the Linux installer installs the required archive support.

CBR extraction is cached privately as needed rather than modifying the original archive.

## Image reader

For image documents, TTL provides:

- Zoom Out
- Zoom In
- Fit
- 100%

`Ctrl` + mouse wheel also adjusts zoom.

## Text and Markdown reader

The text reader includes **Find in document** controls.

Enter a phrase and:

- press Enter or select **Next** to move forward;
- use **Previous** to move backward;
- Shift+Enter moves backward.

Matches are highlighted in the rendered document.

Markdown is rendered as formatted content; plain text remains preformatted.

### Ask this file

Text/Markdown documents also support the split Ask panel. When possible, selecting a cited source scrolls/highlights the corresponding passage in the text pane.

## Source-reader behavior and OCR

For scanned content, TTL can use a private OCR derivative for text/search purposes while leaving the original document untouched. The normal reader still represents the user's library document, not a destructive rewrite of the source.

---

# Search

**Search** performs full-text search across the indexed documents visible to the current user.

Enter a query and select **Search**.

Results show:

- document name;
- virtual folder;
- page number for PDFs when available;
- a matching text snippet.

Selecting a result opens the source document. PDF results open at the reported page.

## Indexed versus visible documents

Search reports:

- the number of indexed documents searched;
- any visible text-capable documents that are not currently indexed.

A document can therefore appear on the Bookshelf but not yet produce Search results until the knowledgebase text stage has processed it.

## Permissions

Player searches include only documents the player is allowed to access.

---

# Knowledgebase administration

Knowledgebase is GM-only and controls the searchable/AI-ready representation of the library.

TTL builds the knowledgebase in three dependent stages:

1. **Extracted Text**
2. **Context Chunks**
3. **Semantic Embeddings**

OCR is a preprocessing operation for documents that do not already contain usable text.

## Knowledgebase status warning

When the library changes or a stage becomes stale, TTL displays **Knowledgebase update required**.

Typical causes include:

- adding a source;
- removing a source;
- a source document changing;
- completing OCR;
- clearing a cache;
- changing the embedding model.

## Update Knowledgebase

This is the normal maintenance action.

**Update Knowledgebase** scans for:

- new documents;
- changed documents;
- documents whose OCR has completed;
- removed documents.

TTL then processes only what needs to change.

For unchanged books, existing downstream work can be reused. In particular, unchanged semantic vectors do not need to be regenerated unnecessarily.

Use this after routine library changes.

## Rebuild Entire Knowledgebase

This deliberately rebuilds the whole chain.

Use it when:

- changing indexing behavior;
- troubleshooting suspected cache corruption;
- intentionally testing a clean rebuild;
- instructed to do so after a significant software change.

It can take considerably longer than an incremental update.

## Stage-status summary

The page identifies whether each stage is:

- **Current**
- **Update needed**

The stages are dependent. Clearing or rebuilding an earlier stage can make later stages stale.

---

# OCR

TTL uses OCR to make scanned/image-based material searchable without modifying the original library file.

The OCR section reports:

- **OCR Documents**
- **OCR Ready**
- **Need OCR**
- **Local OCR Storage**

## Documents detected for OCR

TTL detects scanned PDFs and image-based comic archives that require OCR processing.

OCR output is stored as a persistent local searchable-PDF derivative in TTL's private data area.

The original source remains unchanged.

## OCR All Required

Processes all documents currently identified as requiring OCR.

Only one OCR operation runs at a time.

During processing TTL displays:

- current stage;
- percentage;
- current file;
- current page and total pages when available.

## OCR one document

Each document requiring OCR has its own **OCR** button.

Use this when you want to process only one item rather than the whole queue.

## Cancel OCR

Stops the currently running OCR job.

A cancelled job does not automatically continue.

## OCR dependencies unavailable

If the server cannot find its OCR components, the Knowledgebase page displays a warning and disables OCR actions.

Use the installation/troubleshooting documentation to repair the packaged OCR components.

## After OCR completes

OCR completion marks the knowledgebase as needing an update.

TTL intentionally does **not** automatically launch a potentially expensive text/chunk/embedding build after OCR. The GM chooses when to run **Update Knowledgebase**.

## Source files remain read-only

OCR does not replace, rewrite, annotate, or otherwise modify the source PDF/comic archive. This is deliberate so TTL can operate against read-only shares.

---

# Knowledgebase maintenance controls

In addition to the normal Update/Rebuild controls, the page exposes the individual stages for maintenance.

## Temporary / Orphaned Cache

TTL may create local extraction caches for formats such as CBR.

**Clean Temporary / Orphaned Cache** removes abandoned, obsolete, or orphaned temporary material while preserving valid persistent data.

This is housekeeping and is not the same as clearing the searchable knowledgebase.

## Extracted Text

The Extracted Text section reports text-cache status and storage.

Controls include:

### Build / Refresh Text

Processes the extracted-text stage.

### Rebuild All Text

Forces every eligible source document through text extraction again.

### Clear

Deletes the disposable extracted-text cache.

Clearing text makes dependent context chunks and embeddings stale.

## Context Chunks

Chunks are the bounded passages used by retrieval and AI.

Controls include:

### Rebuild All Chunks

Regenerates chunks from documents with current extracted text.

### Clear

Deletes the chunk cache.

Embeddings depend on chunks, so clearing chunks also makes the embedding stage stale.

---

# Semantic embeddings and hybrid retrieval

Embeddings provide semantic similarity in addition to literal word matching.

TTL's normal retrieval is hybrid: lexical matching and semantic similarity are combined.

## Embedding Model setting

The GM can choose among three supplied profiles:

### Fast

Model: `sentence-transformers/all-MiniLM-L6-v2`

- fastest ingest;
- good general retrieval;
- 384 dimensions.

### Balanced

Model: `sentence-transformers/all-MiniLM-L12-v2`

- moderate ingest cost;
- strong general retrieval;
- 384 dimensions;
- default selection.

### Semantic Quality

Model: `sentence-transformers/all-mpnet-base-v2`

- significantly slower ingest;
- can be stronger on difficult semantic paraphrases;
- 768 dimensions.

Select a model and press **Apply**.

Changing the selected model means the existing embedding cache no longer represents the selected model. Rebuild embeddings afterward.

The first use of an embedding model may require internet access so TTL can obtain the model. Once cached locally, later builds can use the local copy.

## Embedding status

TTL reports:

- Model
- Vectors
- Dimensions
- Backend
- Cache Size

## Rebuild All Embeddings

Computes semantic vectors for the current chunk corpus.

A progress panel reports the running build.

## Clear

Deletes the semantic embedding cache.

Search based on extracted text can still function, but semantic retrieval is unavailable until embeddings are rebuilt.

## Test Hybrid Retrieval

Knowledgebase contains **Test Hybrid Retrieval**.

This opens TTL's retrieval diagnostic page. It is useful for checking whether the corpus is returning the passages you expect before involving an LLM.

The retrieval test allows:

- query entry;
- virtual-folder scope;
- optional specific-document scope.

Results show:

- source;
- page where available;
- semantic score;
- lexical score;
- retrieved text.

This page is primarily diagnostic. It does not ask the AI to compose an answer.

---

# AI provider settings

AI settings are located at the bottom of Knowledgebase and are GM-administered.

TTL supports:

- **Custom / OpenAI-compatible**
- **OpenAI**
- **Google Gemini**

TTL Server is an AI client. The optional **TTL Local AI Backend** is simply one possible OpenAI-compatible provider.

## Provider

Choose the API type.

### Custom / OpenAI-compatible

Use for:

- TTL Local AI Backend;
- another llama.cpp server;
- another application that exposes a compatible `/v1` API.

### OpenAI

TTL fills in the standard OpenAI API base URL.

### Google Gemini

TTL uses Google's OpenAI-compatible Gemini API endpoint.

## Base URL

For a custom provider, enter its API root, for example:

`http://192.168.1.23:8081/v1`

The exact host and port depend on the provider configuration.

For hosted OpenAI or Gemini, TTL supplies the standard base URL automatically unless the administrator intentionally overrides it.

The URL must begin with `http://` or `https://`.

## Model / Alias

Enter the model identifier expected by the provider.

For TTL Local AI Backend, use the alias displayed/configured by the backend manager.

Default TTL configuration uses:

`qwen3.5-9b-q5`

This is only a default alias; TTL does not assume a model is actually available until the provider is configured.

## Advanced Ask Pipeline Preset

This selects the multi-stage workflow used whenever a user chooses **Advanced** Ask.

Pipeline presets are tuned for particular model behavior. If you change LLMs, you may also want to change or retune the preset.

Basic Ask does not use the full Advanced pipeline.

## API Key

For a provider requiring authentication, enter its API key.

The saved key is:

- stored on the TTL server;
- not displayed again by the web UI.

If a key already exists, leaving the field blank while editing the same provider keeps the stored key.

Switching to OpenAI or Gemini requires a key when one is not already applicable to that provider selection.

A custom provider may use a blank key if the server permits unauthenticated access.

## Timeout (seconds)

Range: **5 to 600 seconds**.

This controls how long TTL waits for an AI-provider request before considering it timed out.

For a slow local model, a larger timeout may be necessary.

## Temperature

Range: **0 to 2**.

Lower values make output more deterministic. Higher values allow more variation.

The default is `0.2`, intentionally conservative for rules/reference answers.

## Max Output Tokens

Range: **64 to 8192**.

This caps the provider's final response length.

The default is `1200`.

This limit concerns generated output, not the size of the searchable knowledgebase.

## Save Provider

Stores the settings without performing a connection test.

## Save & Test Connection

Stores the settings and immediately probes the provider.

A successful test confirms that TTL can reach the API endpoint. When the provider reports model information, TTL can show the available model names returned by that endpoint.

A successful connection test does not by itself guarantee good retrieval quality. The knowledgebase and embeddings still need to be built correctly.

---

# Ask Tabletop Librarian

**Ask** combines the current user's permitted knowledgebase with an AI provider.

If no provider is configured, the page can still display scope controls, but an AI answer cannot be produced until a provider is set up.

## Character context

If the user has available completed characters, Ask can optionally attach one as **Character context**.

This supplies the current character-sheet state to the LLM.

Character context is distinct from rules evidence:

- the character sheet describes the character's current state;
- the knowledgebase supplies rules/reference material;
- character state is not treated as a cited rules source.

A GM can use player characters that the GM is permitted to open.

## Reasoning mode

TTL 1.0 provides:

### Basic - Single retrieval

A simpler retrieval and answer path.

Use Basic for:

- quick fact lookups;
- straightforward rule questions;
- situations where low latency is more important than multi-stage reasoning.

### Advanced - Multi-step retrieval

Uses the GM-selected Advanced Ask pipeline preset.

Depending on the preset, this can include stages such as:

- planning;
- bounded retrieval;
- ranking;
- evidence selection;
- analysis;
- decision;
- rescue retrieval;
- final composition.

Use Advanced for questions requiring synthesis across multiple rules/passages.

Advanced can take substantially longer because it may make several model calls.

## Question

Enter the rules/reference question in natural language.

## Virtual Folder scope

Choose:

- **All visible folders**
- one specific virtual folder.

Folder scope reduces retrieval to a game system, campaign, or other collection and can materially improve relevance when the library contains many unrelated systems.

When Ask is opened from **Ask this folder**, the folder scope is already locked.

## Limit to specific documents

Within the current folder scope, documents can be checked individually.

If none are selected, TTL searches every available document in that scope.

When Ask is opened using **Ask this file**, the document scope is locked to that file.

## Ask

Starts retrieval and AI processing.

The UI displays progress while the request runs.

## Cancel

Cancels the active AI request when cancellation is available.

## Answer information

Completed responses identify information such as:

- model;
- Advanced pipeline preset when applicable;
- elapsed time.

## Sources

TTL displays the retrieved evidence sources used for the answer.

A source includes:

- source document;
- page number for PDFs when available.

Selecting a source opens or focuses the relevant document location when the current reader supports it.

## Important limitation

The answer is generated by the configured LLM. Source citations make the evidence inspectable, but the user should still verify consequential or ambiguous rule interpretations against the cited source text.

---

# Play Workspace

Workspace combines three tools on one screen:

- Ask
- a game document
- a character sheet

It is intended for live play when switching repeatedly between those three views would otherwise be cumbersome.

## Selecting a character

Choose one of the completed characters available to the current user.

For GMs, available player characters can also be included.

## Selecting a document

Choose a visible readable library document.

## Layout buttons

Workspace supports:

- **Search 1/3**
- **Search 2/3**
- **Book Focus**

These change how much space is devoted to Ask versus the book/character panes.

The selected layout is saved by the browser using local browser storage, so the browser can remember the preferred workspace arrangement.

## Default Book

A character can have a preferred Workspace document. When the character is selected and that document is still available to the current user, Workspace uses it automatically.

If there is no valid preference, Workspace falls back to an available document.

---

# Characters

Open **Characters** from the main navigation.

The page contains:

- completed characters;
- saved creation drafts;
- saved advancement drafts;
- New Character;
- character import;
- GM-only System Pack import.

## Player character view

Players see their own completed characters and their own drafts.

## GM character view

GMs see character groups for themselves and other known users.

This lets a GM open a player's stored character directly rather than maintaining a GM-owned duplicate.

## Creation Drafts

A guided creation workflow can be saved before it is complete.

A saved draft remains on the Characters page and can be resumed later.

## Advancement Drafts

Likewise, an in-progress System Pack advancement workflow can be saved and resumed.

---

# Character creation

Select **New Character**.

## System

Choose the installed System Pack.

Each System Pack defines its own fields and workflow. TTL itself does not hard-code one universal character sheet.

## Character name

Enter the character name when the selected pack/workflow requires it.

## Begin Creation

Starts the System Pack's character-creation workflow.

For packs without a guided workflow, TTL can create the basic character directly from the pack schema.

## Guided creation pages

A System Pack may divide creation into steps such as:

- identity;
- species/background choices;
- ability scores;
- skills;
- features;
- equipment;
- spells;
- story information.

The exact pages and controls come from the selected System Pack.

## Rule feedback

TTL can show:

- calculated values;
- rule messages;
- eligibility restrictions;
- selection limits.

Some fields are calculated or restricted according to earlier choices.

## Choice selectors

Reference and multi-reference fields can open searchable picker dialogs.

Depending on the pack, picker features can include:

- search;
- tag filtering;
- eligibility information;
- **Hide unavailable**;
- descriptions;
- custom entries.

## Hide unavailable

When enabled, options whose requirements are not currently met are hidden from the selector.

When disabled, unavailable options can remain visible for reference but are identified as unavailable.

## Custom entries

A System Pack can allow a `<Custom>` choice for a field.

In Generic D20, this is used for skills and feats.

Selecting `<Custom>` creates an editable row where the player can provide:

- Name
- Description

Custom descriptive entries do not automatically acquire mechanical effects defined for standard compendium entries.

## Collection rows

Pack-defined repeatable collections, such as weapons or armor, may provide:

- add row;
- remove row;
- reorder controls;
- standard-reference autofill;
- custom-item fields.

## Save & Exit

Stores the creation draft and returns to the Characters page.

Use this when creation is not complete.

## Back / Next

Moves among workflow steps.

Rules can prevent progress when a required choice is missing or a blocking validation error remains.

## Finish Character

Applies the workflow's final calculations/changes and saves the completed character.

## Discard Draft

Deletes the in-progress creation draft.

This does not delete a previously completed character because the draft is a separate object.

---

# Playing and configuring a character

Opening a completed character provides two conceptually different uses:

- **Play**
- **Configure**

The exact controls vary by System Pack.

## Play mode

Play mode is for values the pack marks as safe to change during play, such as:

- current resources;
- temporary state;
- other `play_editable` fields.

Fields intended to represent core build decisions remain protected.

TTL supports autosave behavior for appropriate character changes so normal play-state edits can be persisted without treating them as a complete rebuild of the character.

## Configure mode

Configure mode exposes the character's configuration/editing controls.

System Packs can identify core creation fields that are normally locked. TTL can allow an individual core field to be intentionally unlocked for correction rather than making every fundamental choice permanently editable all at once.

This is useful for:

- correcting an entry error;
- incorporating a GM-approved rebuild;
- manually adjusting information that a pack cannot automate.

## Rules panel

The character UI can display active rules/issues associated with current values.

Calculated values are re-evaluated from the character's stored data and System Pack rules.

## Save Configuration

Stores configuration-mode edits after validation.

## Delete Character

Permanently removes that stored character.

Export the character first if you want a portable backup.

## Default Book

Configure mode includes **Default Book**.

Options include:

- **Automatic (first available)**
- a visible library document.

This preference controls which document Workspace selects by default for that character.

The selection must still be available to the current user when Workspace is opened. If it becomes unavailable, TTL falls back rather than bypassing permissions.

---

# Temporary modifiers

System Packs can expose numeric fields that support temporary effects.

Examples might include a temporary bonus to:

- Armor Class;
- an ability score;
- a skill;
- another calculated/numeric field allowed by the pack.

The character page provides **Temporary Modifier** controls for eligible fields.

## Label

A human-readable description, for example:

- `Blessing`
- `Poisoned`
- `Magic shield`

## Operation

Supported operations are:

- **Add**
- **Subtract**
- **Multiply**
- **Override**

### Add

Adds the modifier value to the base/effective value.

### Subtract

Subtracts the value.

### Multiply

Multiplies by the specified value.

### Override

Temporarily replaces the effective value.

## Value

Must be numeric.

TTL stores an integer when the entered value is a whole number; otherwise it retains the decimal value.

## Duration

An optional descriptive duration can be recorded.

TTL does not interpret arbitrary duration text as a timer. It is a note for the player/GM unless the System Pack provides other behavior.

## Removing effects

Individual modifiers can be removed. Eligible fields can also have their temporary modifiers cleared.

Temporary effects are stored with the character separately from its permanent base configuration.

---

# Character advancement

A System Pack can define advancement actions.

Examples can include:

- level advancement;
- milestone changes;
- other system-specific progression.

The available actions come entirely from the installed System Pack.

## Begin advancement

Select an available advancement action from the character.

TTL creates an advancement draft.

## Advancement workflow

Like creation, advancement can contain multiple steps with:

- choices;
- calculated values;
- rule checks;
- eligibility;
- repeatable collection fields.

## Save & Exit

Stores the advancement draft without changing the completed character yet.

## Back / Next

Moves through the advancement workflow.

## Apply Advancement

Commits the completed advancement to the character.

## Discard Advancement

Deletes the advancement draft without applying it.

This makes it possible to explore an advancement workflow without immediately changing the authoritative character.

---

# Character import and export

TTL uses `.ttlchar` packages for portable characters.

## Export

Open a character and use its export function.

The exported package contains the authoritative TTL character record and metadata required for portability.

Keep exports as backups or move characters between TTL servers.

## Import Character

On the Characters page, choose a `.ttlchar` file.

The matching System Pack must be installed locally so TTL can validate the imported data.

### Import for

GMs can choose the target owner.

Players import into their own account.

### Character ID collision

If the same character ID already exists, TTL offers:

- **Import as a new copy**
- **Replace existing character**

Use **new copy** when both versions should coexist.

Use **replace** only when the imported package should become authoritative for the existing character.

## Incompatible/missing System Pack

If TTL cannot open a saved character using the currently installed System Pack, it shows a recovery page rather than silently altering the character.

The character can still be deleted from recovery if necessary.

Normally the better solution is to install the required compatible System Pack.

---

# System Packs

System Packs define game-system-specific character behavior.

A pack can supply:

- character schema;
- defaults;
- calculated values;
- validation;
- compendium entries;
- eligibility rules;
- selection limits;
- creation workflow;
- advancement workflow;
- character-sheet layout;
- assets.

System Packs are packaged as `.ttlsys` files.

## Import System Pack

GM-only.

From Characters:

1. choose a `.ttlsys` package;
2. select **Import System Pack**.

TTL validates the package before installing it.

If the System Pack ID already exists, the imported pack can replace the existing version.

## Replacement and character migration

When a replacement version is installed, TTL can migrate compatible existing character data.

The import report identifies:

- installed name/version;
- prior version when replaced;
- migrated-character count;
- migration warnings.

Review warnings. A successful pack replacement does not guarantee that every semantic change in a custom game system can be automated perfectly.

## Security model

System Pack rules use TTL's constrained data/rule systems rather than arbitrary pack-supplied Python execution.

Unsafe archive paths/content are rejected by the package importer.

For pack creation details, see [System Packs](SYSTEM_PACKS.md).

---

# Built-in Generic D20

TTL 1.0 ships with **Generic D20 1.0**, based on SRD 5.2.1.

It serves two purposes:

1. a useful playable 5E-compatible example;
2. a comprehensive demonstration of TTL's System Pack framework.

Generic D20 includes SRD-derived choices for:

- classes;
- subclasses;
- backgrounds;
- species;
- skills;
- feats;
- weapons;
- armor;
- cantrips;
- spells;
- languages and related choices.

## Guided creation

The built-in workflow guides a level-1 character through the major decisions and calculated values.

## Species-dependent choices

The interface conditionally shows species-specific options only when relevant.

Size is automatically derived where SRD rules make it fixed. Species with legitimate Small/Medium choice retain that choice.

## Background ability boosts

The workflow enforces the ability-boost pattern permitted by the chosen background.

Unavailable boost choices are shown as unavailable/read-only rather than being submitted as missing values.

## Skills

Skill selectors provide:

- standard SRD skills;
- concise descriptions;
- eligibility/selection limits;
- `<Custom>`.

Selected skills display in a Name/Description table.

`<Custom>` allows the player to add a freeform skill name and description for campaign-specific additions.

## Feats

Feats use the same Name/Description table presentation.

The selector uses existing feat descriptions and also permits `<Custom>` descriptive feats where that field supports them.

## Weapons and armor

Standard weapons and armor are selected from compendium dropdowns and automatically populate their standard game data.

The blank special choice is labeled **Custom**.

### Custom weapon

When Weapon = **Custom**, the custom attack-name field becomes visible.

When a standard weapon is selected, that custom field is hidden.

### Custom armor

When Armor = **Custom**, the custom armor-name field becomes visible.

When standard armor is selected, that custom field is hidden.

For a standard item with a campaign-specific special property, such as "Longsword, +1 against goblins," retain the normal standard item and document the variation in the row's notes rather than converting it to an entirely custom item.

## Spellcasting

Spell and cantrip sections are conditionally shown only for characters whose current class/species choices make those controls relevant.

## Derived values

Generic D20 calculates common derived values through the System Pack rule engine rather than hard-coded TTL logic.

## Advancement

The pack supports level advancement through level 20, while deliberately leaving unusual/custom campaign decisions available for manual documentation where complete automation would be inappropriate.

## Generic D20 is not an official Wizards product

SRD-derived content retains its CC BY 4.0 licensing and attribution requirements. See the repository's third-party license/notice documentation.

---

# The bundled D20 SRD bookshelf folder

A clean release installation initializes the Bookshelf with **D20 SRD**.

It contains:

- the bundled `SRD_CC_v5.2.1.pdf`;
- project-created custom cover artwork.

The PDF is installed as release/reference content rather than copied into the user's upload staging area.

TTL registers it as a normal file source of the virtual folder.

## Why it is included

It gives a first-time user:

- something visible on an otherwise empty Bookshelf;
- an example of the reader;
- source material corresponding to the built-in Generic D20 System Pack;
- a document that can be indexed for Search/Ask.

## Knowledgebase is not prebuilt

The presence of the SRD PDF on the Bookshelf does not mean extracted text, chunks, and semantic embeddings have already been built for the user's installation.

A GM should run **Update Knowledgebase** after initial setup if Search/Ask functionality is desired.

## Deleting the D20 SRD folder

The folder is only seeded when the library has never been initialized.

If the GM deletes it, TTL does not keep recreating it at startup.

A completely purged fresh installation can seed it again because that installation has no prior library state.

---

# Recommended operating workflow

For a new server, a practical setup sequence is:

1. Create the initial GM account.
2. Confirm the bundled **D20 SRD** folder appears as expected.
3. Open Library and create any additional virtual folders.
4. Add physical directories/files or assign uploads.
5. Configure player/GM visibility.
6. Set folder covers and manual document covers as desired.
7. Create player accounts.
8. Review Knowledgebase for scanned documents.
9. Run OCR for required documents.
10. Select an embedding model.
11. Run **Update Knowledgebase**.
12. Configure an AI provider if Ask will be used.
13. Select the Advanced Ask pipeline appropriate for the LLM.
14. Use **Save & Test Connection**.
15. Test Hybrid Retrieval with representative rule questions.
16. Test Basic Ask.
17. Test Advanced Ask.
18. Create/import any additional System Packs.
19. Create characters.
20. Set each active character's Default Book if Workspace will be used during play.

For ongoing use:

- add/remove source material in Library;
- run OCR only for newly detected image-based documents;
- use **Update Knowledgebase** after library/OCR changes;
- use full rebuild controls only for maintenance or when intentionally changing underlying models/index behavior.

---

# What TTL stores and what it does not modify

Understanding the distinction between **source library data**, **persistent TTL data**, and **disposable cache data** is useful when administering the server.

## Original library files

When a GM adds a physical source, TTL references the existing file/directory.

TTL does not need to:

- rename it;
- move it;
- rewrite it;
- write OCR text back into it;
- insert cover art into it.

This makes read-only libraries practical.

## Persistent TTL data

Persistent application data includes things such as:

- setup/configuration;
- user accounts;
- virtual folder definitions;
- visibility settings;
- manual covers;
- staged uploads;
- characters;
- creation drafts;
- advancement drafts;
- System Pack state/backups;
- OCR derivatives;
- AI provider settings;
- embedding-model selection;
- locally cached embedding model files.

On a packaged installation, these reside in TTL's writable application-data locations rather than the source bookshelf.

## Cache data

Disposable/rebuildable cache includes things such as:

- generated automatic covers;
- PDF text-status information;
- extracted text;
- chunks;
- semantic vectors/index metadata;
- temporary CBR extraction data.

The exact installed paths are platform-specific and are documented in [Installation](INSTALLATION.md).

## Bundled release resources

The Server release itself includes resources such as:

- built-in Generic D20 System Pack;
- SRD PDF;
- SRD cover artwork;
- application static assets such as the favicon.

These are part of the installed application payload and are distinct from user-created data.

---

# Common questions

## I added a book but Search cannot find it. Why?

The Bookshelf scans source files directly, but Search uses the indexed extracted-text cache.

Run **Update Knowledgebase**.

If the document is scanned/image-only, OCR it first and then update the knowledgebase.

## Why does Ask not know about a newly added book?

For the same reason: Ask retrieves from the knowledgebase rather than reading the whole file ad hoc for every question.

OCR if needed, then run **Update Knowledgebase**.

## Do I need semantic embeddings for ordinary Search?

Ordinary full-text Search primarily depends on extracted/indexed text. Embeddings are needed for semantic/hybrid retrieval used by the RAG/Ask workflow.

## Can players see GM-only material through Ask?

TTL constructs player retrieval scope from player-visible library content. GM-only documents are excluded from the player's available scope.

## Does OCR change my PDF?

No. TTL creates a private derivative.

## Does removing a source delete my files?

No. It removes TTL's source relationship.

The exception is the separate **Delete** action for a staged upload, which intentionally deletes that copy from TTL's upload storage after it is no longer assigned as a library source.

## Why is a network-share book still remembered when the share goes offline?

TTL is conservative about temporary source outages. It keeps persistent manifest information so an unavailable mount is not automatically treated as deletion.

## Why is the AI provider connection test successful but answers are poor?

Connectivity and retrieval quality are separate.

Check:

1. the correct books are indexed;
2. OCR completed where required;
3. chunks are current;
4. embeddings are current;
5. Hybrid Retrieval returns relevant passages;
6. the correct model alias is configured;
7. the Advanced Ask pipeline is appropriate for that model.

## Does TTL Local AI Backend have to be installed on the Server machine?

No. It can run on another LAN machine as long as the TTL Server can reach its OpenAI-compatible API address.

## Can I use OpenAI or Gemini instead?

Yes. Choose the provider in Knowledgebase and provide the appropriate model/API key.

## Can I use TTL without AI?

Yes. AI configuration is optional.

## Can a GM edit a player's character?

A GM can open player characters directly. TTL preserves ownership; it does not create a GM copy merely because the GM is viewing/configuring it.

## Can I back up a character individually?

Yes. Export it as `.ttlchar`.

For full-server backup and data locations, use the installation/administration documentation and back up the persistent TTL data directory.

## What happens if I replace a System Pack?

TTL validates the new `.ttlsys`, installs it, and attempts compatible character migration while reporting warnings that require review.

## Why can't a stale character open?

Its saved schema/System Pack requirements may not match the currently installed pack. Install the appropriate compatible System Pack or use the recovery page to remove the character if it is no longer needed.

## Can I create campaign-specific skills or feats in Generic D20?

Yes. Choose `<Custom>` where available and enter the freeform Name and Description.

Those custom entries are descriptive unless separate mechanics are modeled elsewhere.

## How should I represent a slightly modified standard weapon?

Keep the standard weapon selected so its standard statistics continue to autofill, then record the special property in Notes.

Use **Custom** when the item itself does not appropriately correspond to a standard compendium item.

## Why doesn't the D20 SRD folder reappear after I delete it?

That is intentional. It is a first-library seed, not a mandatory folder.

---

# Additional documentation

- [Installation](INSTALLATION.md): packaged installation, service locations, upgrades, uninstall.
- [Knowledgebase, OCR, and AI](AI_AND_KNOWLEDGEBASE.md): technical overview of the searchable/AI pipeline.
- [TTL Local AI Backend](AI_BACKEND.md): local llama.cpp backend manager.
- [Advanced Ask Pipeline Presets](ADVANCED_AI_PIPELINES.md): preset format and tuning.
- [System Packs](SYSTEM_PACKS.md): System Pack format and authoring.
- [Building Release Artifacts](BUILDING.md): release builders.
- [Troubleshooting](TROUBLESHOOTING.md): common operational problems.
