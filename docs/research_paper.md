# CodeVault: A Git-Aware Local Shadow Backup System for Uncommitted Source Code

**Bhavesh Lakhmani**
*[Department, Institution]* · *[email]*

## Abstract

Version control protects the work that a developer chooses to commit. It says nothing about the hours of edits that sit between two commits, and those are the edits most exposed to an accidental overwrite, a careless delete, or an automated rewrite by an AI coding assistant. This paper presents CodeVault, a small open-source tool written in Python that keeps a labelled snapshot of every saved source file, entirely on the developer's own machine. CodeVault stores snapshots under their SHA-256 fingerprint so that repeated saves cost nothing, records metadata in SQLite, and writes every file atomically so that a crash cannot corrupt the store. Two additions distinguish it from earlier local-history features. First, it compares each snapshot with the contents of the git repository and classifies it as pushed, committed but not pushed, or present only on the local machine, which tells the developer exactly which work would be lost if the laptop failed. Second, it attributes snapshots to the tool that produced them, using hooks for Claude Code and labelled checkpoints for other agents. We describe the design, the git classification method, and the implementation, and we report measurements from a prototype: a snapshot of a source file up to about 67 KB took under one millisecond at the median on the test machine, and one hundred repeated saves of unchanged content added no storage. We also discuss limitations, chiefly that CodeVault is an emergency recovery aid and not a substitute for a remote backup.

**Keywords:** version control, local history, backup, file system monitoring, content-addressable storage, developer tools, AI-assisted programming

## 1. Introduction

A student working on an assignment, or a developer on a small project, tends to commit rarely and edit constantly. Git guards the commits. The state of the working tree between commits is guarded by nothing except the editor's undo buffer, which is discarded when the editor closes. A single mistaken command, such as removing the wrong path or saving the wrong version over a file, can therefore destroy work that no tool can bring back.

Two recent habits make the gap wider. Developers now run coding assistants that rewrite files directly on disk, sometimes across many files in one step. When the result is wrong, the previous version often exists nowhere: it was never committed, and the assistant keeps no history of its own. In addition, many developers treat a remote such as GitHub as their backup, although a remote holds only what has been pushed. Work that is committed but not pushed, and work that is not committed at all, is local-only, and the developer has no quick way to tell which files are in that state.

CodeVault addresses both problems. It runs in the background of a project folder, saves a snapshot each time a source file is saved, and lets the developer list, compare and restore any earlier version. It is designed to sit beneath Git rather than replace it. The main contributions of this work are:

1. A design for a dependency-light local snapshot store that is safe against crashes and avoids storing duplicate content.
2. A method for classifying every stored snapshot by its position in the git history, using the git object hash of the content, so that the developer can see which snapshots exist only locally.
3. A lightweight way to attribute snapshots to AI coding tools, so that an assistant's edits can be found and undone.
4. A local web dashboard and a measured evaluation of the prototype.

The remainder of the paper reviews related work (Section 2), describes the design (Section 3) and the implementation (Section 4), presents the evaluation (Section 5), discusses limitations (Section 6) and concludes (Section 7).

## 2. Background and Related Work

**Version control.** Git stores every object, including file contents, under a name derived from a cryptographic hash of that content, which makes it in effect a content-addressable file system with a version control interface on top [1]. Its guarantees begin at the moment of a commit. Anything not yet committed is outside its reach, and that is the region CodeVault targets.

**Local history in editors.** Integrated development environments already offer some protection. The local history feature in JetBrains IDEs records changes to a project independently of version control, lets the user label a state, and can restore a deleted file; by default it keeps revisions for the last five working days, and it is described by its vendor as no replacement for real version control [2]. Such features are tied to one editor and to its storage location, so they do not help when a change is made by a command-line program or an assistant running outside the editor, and they offer no view of how the recorded states relate to the git history. CodeVault works at the file system level and is therefore independent of any editor.

**Content-addressed archival storage.** Addressing a block by the hash of its contents gives two properties at once: identical data is stored once, and stored data cannot be silently replaced. Quinlan and Dorward developed this idea for archival storage in the Venti system, where it enforces a write-once policy and lets duplicate blocks be coalesced [3]. CodeVault applies the same principle at a much smaller scale, using SHA-256 [4] as the fingerprint, but it adds retention and pinning because a developer's working history is not meant to be kept forever.

**Shadow-repository tools.** A number of small tools keep working-tree snapshots inside a second git repository or in private git references, so that uncommitted work can be rolled back without touching the project's own history. Examples include d4-snap, which stores checkpoints in a separate bare repository [7], and gitundo, which stores automatic and named checkpoints as git references [8]. These tools use git as their storage format. CodeVault takes the opposite direction: its store is independent of git, and git is consulted read-only to label each snapshot. We did not find a tool whose purpose is to report how much of the local history is already on a remote, though our search was informal and cannot rule one out.

**File system monitoring.** The watchdog library provides a Python interface to the change notifications of the operating system, with event classes for creation, modification, deletion and move, and a polling fallback for platforms without native support [5]. CodeVault builds its watcher on this library and handles two practical problems that raw events leave open: editors that write a temporary file and rename it, and bursts of events for a single save.

**Crash-safe metadata.** SQLite guarantees that all of the changes in a transaction either take effect or none do, and its write-ahead logging mode lets readers continue while a writer appends to the log [6]. This suits a background process that writes while a command-line tool or the dashboard reads.

CodeVault's position among these is narrow by design. It is not a version control system, an editor feature or a cloud backup. It is a local safety net whose snapshots are compared against Git in order to say how safe each of them is.

## 3. Design

### 3.1 Goals and scope

The design follows five goals: lose no more than a few seconds of saved work; require no effort once started; avoid storing the same content twice; make recovery simple and never destructive by surprise; and keep the tool small enough to install in one command on macOS, Linux and Windows. It deliberately excludes branching, merging, remotes, accounts and cloud synchronisation. All data stays in a hidden folder inside the project.

### 3.2 Architecture

The system has five parts. A **watcher** receives file system events. A **backup engine** decides whether an event produces a snapshot. A **store** keeps the snapshot files and their SQLite metadata. A **recovery engine** provides history, differences, timelines and restoration. A **front end** exposes these through a command-line interface and a local web dashboard. A background **daemon** manager runs the watcher without a terminal and ensures that only one instance serves a project.

### 3.3 Snapshot creation

When a monitored file is saved, the watcher waits for a short debounce interval (one second by default) so that a burst of events from one save becomes a single snapshot. The engine then reads the file and computes its SHA-256 fingerprint. If the fingerprint equals that of the newest snapshot of the same file, nothing is stored. Otherwise the content is copied to the store through a temporary file that is renamed into place, so a partial write can never be mistaken for a snapshot, and a row describing it (path, time, fingerprint, size, event type, optional note) is committed to SQLite. Directories such as `.git`, `node_modules` and virtual environments, together with user-defined glob patterns, are ignored.

### 3.4 Retention and pinning

Unbounded history would grow without limit, so snapshots beyond a per-file count (10 in the shipped configuration) or older than an age limit (30 days by default) are removed during cleanup. A snapshot can be pinned, and pinned snapshots are never removed. A preview mode lists what a cleanup would delete before anything is touched.

### 3.5 Safe restoration

Restoring a file first snapshots its current content under a distinct event type, so a restore can itself be undone. Before any bytes are written back, the stored snapshot is re-hashed, and a snapshot whose fingerprint no longer matches is refused. A separate verification command walks the whole store and reports snapshots that are valid, corrupted or missing. Deleted files are recorded as events, which allows a file removed from disk to be listed and recovered, and a whole project can be restored to a chosen moment.

## 4. Git-Aware Classification and AI Attribution

### 4.1 Which snapshots does GitHub have?

The question a developer cares about is not only whether a snapshot exists, but whether the work in it exists anywhere else. CodeVault answers by comparing contents, not paths or timestamps. Git names a file's content by hashing a short header, the word *blob* and the content length, followed by the content itself. CodeVault computes this value for each snapshot and compares it with the blob names recorded for the same path in two places: the current commit, and the upstream branch that the current branch tracks. Reading these names is a read-only operation on the repository.

This yields three states:

| State | Condition | Meaning |
|---|---|---|
| Pushed | The blob appears in the upstream commit | The content is on the remote |
| Committed | The blob appears in the local commit only | In local git history, not yet pushed |
| Local | The blob appears in neither | Only the CodeVault snapshot holds it |

Because the comparison is by content, a snapshot that matches a commit made years ago is correctly reported as safe, and a file that was edited and then reverted to the committed text is not reported as at risk. The dashboard lists every file whose only copy of some version is the local snapshot, and can also report uncommitted changes and commits that have not been pushed. A user-triggered fetch refreshes the remote state.

### 4.2 Attributing edits to AI tools

A file watcher sees that a file changed but not who changed it. For assistants that support hooks, CodeVault installs a configuration in the project so that the assistant calls CodeVault immediately before and immediately after each file edit; the two snapshots are labelled with the tool name and an event type that distinguishes the before state from the edit. For tools without hooks, a command takes a labelled checkpoint of chosen files or the whole project, to be run before and after an agent session. Labels appear in file histories, in a timeline filter for AI edits, and as a distinguishing mark on the dashboard. The mechanism is deliberately simple: it records what the tool reports about itself and does not try to detect AI-generated text.

## 5. Implementation and Evaluation

### 5.1 Implementation

CodeVault is implemented in Python (about 4,300 lines in the core package and web server) with one runtime dependency, the watchdog library. Metadata is kept in SQLite with write-ahead logging, foreign keys and a busy timeout enabled. The dashboard is served by the standard library HTTP server, binds to the loopback address only, accepts state-changing requests only as JSON, and serves a landing page and a single-page dashboard from static files with no build step. The automated test suite contains 124 tests and runs on macOS, Linux and Windows in continuous integration.

### 5.2 Measurements

We measured the prototype on one machine (macOS, Python 3.14, local solid-state storage) using synthetic Python-like source text. Each size was saved thirty times with new content, and the time of the snapshot call was recorded. To test deduplication, an unchanged file was saved one hundred times and the size of the store was compared before and after.

| File size | Median time per snapshot | Slowest of 30 |
|---|---|---|
| 0.7 KB | 0.88 ms | 3.4 ms |
| 6.7 KB | 0.87 ms | 1.8 ms |
| 66.8 KB | 0.84 ms | 1.8 ms |

One hundred saves of unchanged content produced a storage increase of 0 bytes and a median call time of 0.37 ms, because the engine returns after comparing fingerprints. Snapshot time was dominated by fixed costs, which are one read, one atomic copy and one database transaction, rather than by file size in this range. These figures meet the target in the requirements document of under 50 ms per snapshot with a wide margin.

### 5.3 Threats to validity

The measurements come from a single machine and synthetic content, and do not include the debounce delay (one second by default) that separates a save from its snapshot. Storage figures reflect an idealised case of exact duplicates and say nothing about the growth of history under real editing, which depends on retention settings. We did not evaluate the system with a user study, so claims of usability are not supported by evidence beyond the authors' own use.

## 6. Limitations and Future Work

CodeVault is an emergency local recovery tool. It lives on the same disk as the project, so a failed disk or a stolen laptop destroys both; it does not replace remote backup or a pushed branch. Only text source files with configured extensions are monitored, and large binary files are out of scope. A change made between a save and its debounced snapshot is not captured, and a file saved and deleted within that interval may leave no history. The git classification compares content at the same path, so a file that was moved and then committed under a new name is reported according to its new path. Attribution relies on cooperation from the tool, and an edit made by an assistant without hooks and without a checkpoint is recorded as an ordinary save.

Future work includes block-level storage for large files, optional encrypted off-site copies, a classification that follows renames through git history, and a controlled study in which participants recover from deliberately injected mistakes with and without the tool.

## 7. Conclusion

The region between two commits is where most accidental loss happens and where version control offers nothing. CodeVault fills it with a small, local, crash-safe snapshot store, and it adds the information a developer actually needs when something goes wrong: which of the saved versions GitHub already has, and which were written by an AI assistant. The prototype is fast enough to be invisible, wastes no space on duplicate saves, and is open source and installable with a single command. Its code is available at https://github.com/Dev57668/python-programms.

## References

[1] S. Chacon and B. Straub, "Git Internals: Git Objects," in *Pro Git*, 2nd ed. Apress, 2014. https://git-scm.com/book/en/v2/Git-Internals-Git-Objects

[2] JetBrains, "Local History," *IntelliJ IDEA Help*. https://www.jetbrains.com/help/idea/local-history.html

[3] S. Quinlan and S. Dorward, "Venti: A New Approach to Archival Data Storage," in *Proc. 1st USENIX Conference on File and Storage Technologies (FAST)*, Monterey, CA, 2002, pp. 89–102. https://www.usenix.org/conference/fast-02/venti-new-approach-archival-data-storage

[4] National Institute of Standards and Technology, *Secure Hash Standard (SHS)*, FIPS PUB 180-4, 2015. https://csrc.nist.gov/pubs/fips/180-4/upd1/final

[5] Watchdog contributors, "watchdog: Python API and shell utilities to monitor file system events." https://python-watchdog.readthedocs.io/

[6] SQLite Consortium, "Atomic Commit in SQLite" and "Write-Ahead Logging." https://www.sqlite.org/atomiccommit.html and https://www.sqlite.org/wal.html

[7] "d4-snap," Python Package Index. https://pypi.org/project/d4-snap/

[8] "gitundo," Python Package Index. https://pypi.org/project/gitundo/
