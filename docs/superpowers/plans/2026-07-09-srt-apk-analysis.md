# SRT APK Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the SRT Android APK, identify all internal network APIs and important client-side logic, and produce a reviewed Markdown analysis document.

**Architecture:** Keep generated reverse-engineering artifacts under `build/` and hand-written findings under `docs/analysis/`. Use both `apktool` resources and `jadx` Java output so endpoint strings, resource values, manifest declarations, request builders, and crypto/session logic can be cross-checked.

**Tech Stack:** APK ZIP inspection, apktool, jadx, POSIX shell tools, ripgrep, Markdown.

## Global Constraints

- Do not modify `srt.apk`.
- Do not commit generated decompilation output unless explicitly requested.
- Do not include secrets, tokens, or live abuse instructions in the final document.
- Prefer exact source references to decompiled files and line numbers for every API and logic finding.

---

### Task 1: Baseline Artifact Inventory

**Files:**
- Read: `srt.apk`
- Create: `docs/analysis/srt-apk-analysis.md`

**Interfaces:**
- Produces: APK hash, size, package/version metadata, and analysis environment notes for the final document.

- [x] **Step 1: Capture file identity**

Run: `ls -lh srt.apk && file srt.apk && shasum -a 256 srt.apk`

Expected: APK size, ZIP file type, and SHA-256 digest.

- [x] **Step 2: Capture APK archive layout**

Run: `zipinfo -1 srt.apk | sort > build/apk-file-list.txt`

Expected: `build/apk-file-list.txt` contains manifest, dex files, resources, native libraries, and assets.

- [x] **Step 3: Start the final document**

Create `docs/analysis/srt-apk-analysis.md` with sections for summary, artifact metadata, API inventory, request/response logic, security/session logic, and evidence references.

### Task 2: Decode Resources and Manifest

**Files:**
- Create: `build/apktool/`
- Modify: `docs/analysis/srt-apk-analysis.md`

**Interfaces:**
- Consumes: `srt.apk`
- Produces: decoded `AndroidManifest.xml`, resources, network security config, and permissions/activity/service metadata.

- [x] **Step 1: Decode with apktool**

Run: `apktool d -f srt.apk -o build/apktool`

Expected: `build/apktool/AndroidManifest.xml` and decoded resources exist.

- [x] **Step 2: Extract manifest facts**

Run: `rg -n "package=|uses-permission|activity|service|receiver|provider|networkSecurityConfig|usesCleartextTraffic" build/apktool/AndroidManifest.xml build/apktool/res -g '*.xml'`

Expected: package identity, permissions, exported components, and network security settings.

- [x] **Step 3: Search decoded resources for URLs and API constants**

Run: `rg -n "https?://|api|srt|korail|etk|app|host|server|port" build/apktool/res build/apktool/assets build/apktool/smali*`

Expected: candidate hosts, path fragments, and configuration strings.

### Task 3: Decompile Java/Kotlin Logic

**Files:**
- Create: `build/jadx/`
- Modify: `docs/analysis/srt-apk-analysis.md`

**Interfaces:**
- Consumes: `srt.apk`
- Produces: readable source tree for endpoint, request assembly, crypto, persistence, and UI flow references.

- [x] **Step 1: Decompile with jadx**

Run: `jadx -d build/jadx srt.apk`

Expected: `build/jadx/sources/` exists with Java source files.

- [x] **Step 2: Extract all URL-like strings**

Run: `rg -n "https?://|[A-Za-z0-9_.-]+\\.(co\\.kr|com|net|kr)|/[^\"' ]{2,}" build/jadx/sources build/jadx/resources > build/jadx-url-candidates.txt`

Expected: candidate host/path list for review.

- [x] **Step 3: Locate networking implementations**

Run: `rg -n "HttpURLConnection|OkHttp|Retrofit|Volley|WebView|loadUrl|postUrl|SOAP|Socket|URLConnection|Request|Response|execute\\(|openConnection|setRequestProperty|Content-Type|User-Agent" build/jadx/sources`

Expected: decompiled source references for request execution and headers.

### Task 4: API Inventory and Logic Analysis

**Files:**
- Modify: `docs/analysis/srt-apk-analysis.md`

**Interfaces:**
- Consumes: outputs from Tasks 2 and 3.
- Produces: grouped API table with method, URL/host/path, parameters, trigger flow, headers/session behavior, and evidence reference.

- [x] **Step 1: Normalize candidate endpoints**

Run source searches for URL builders, base URLs, constants, and path concatenation. Confirm each API by tracing from UI or service call site to network send method.

- [x] **Step 2: Classify core user flows**

Document login/session, station/search metadata, train schedule lookup, reservation flow, payment-related handoff, ticket lookup/cancel/refund, app update/config, push/device registration, and WebView flows when present.

- [x] **Step 3: Document request mechanics**

For each network stack, record HTTP method, content type, encoding, headers, cookies/session handling, encryption/signing, device/app identifiers, and timeout/retry behavior.

### Task 5: Final Verification

**Files:**
- Modify: `docs/analysis/srt-apk-analysis.md`

**Interfaces:**
- Consumes: final Markdown document.
- Produces: verified documentation with reproducible evidence.

- [x] **Step 1: Run a final evidence search**

Run: `rg -n "https?://|HttpURLConnection|openConnection|setRequestProperty|WebView|loadUrl|postUrl|encrypt|decrypt|Cipher|MessageDigest|SHA|AES|RSA" build/jadx/sources build/apktool`

Expected: no major networking or crypto areas are missing from the document.

- [x] **Step 2: Check generated document references**

Run: `rg -n "build/(jadx|apktool)" docs/analysis/srt-apk-analysis.md`

Expected: API and logic findings include source references.

- [x] **Step 3: Review scope gaps**

Record any limitations caused by obfuscation, packed/native code, encrypted strings, or unreachable dynamic behavior.
