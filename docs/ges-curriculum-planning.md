# GES lesson notes and schemes of learning

This change belongs to Nyansa Teacher Copilot (Pillar C). Suku360 remains the
institutional record and report-card authority.

## Assessment and implementation

The existing Django modular monolith uses server-rendered templates, tenant
membership checks, subject-scoped forms, PostgreSQL in production and SQLite
for local development. The dashboard owns lesson generation, versioned review,
PDF/Word lesson exports, and private teacher-owned schemes. It previously
generated only week/topic schemes and asked the model to infer curriculum codes.
Lesson exports omitted the teacher's name and a vetting/signature section.

The supplied RME Basic 7–9 sample defines the layout reference. Its curriculum
wording is not always identical to the NaCCA PDFs, so the PDFs take precedence
for content standards and indicators. Attached text is reference data, not an
instruction source. This is an incremental change within the existing dashboard;
no institutional modules, learner intelligence, intervention records, Student
360 APIs, authentication or tenancy architecture are replaced.

## Teacher workflow

- Lesson forms accept a printable teacher name, falling back to the signed-in
  user's profile name. New versions snapshot this field. Existing approval locks
  and reopening rules also protect it.
- Lesson previews, PDF and Word exports include teacher name, the three lesson
  phases, and a final headteacher name/date/signature/remarks section.
- Date Vetted comes from an approved note's server-recorded review timestamp.
  A draft, returned or reopened note has blank vetting fields. The signature is
  always a blank line; generation never fabricates a signature or approval.
- A termly scheme includes Week, Strand, Sub-Strand, Content Standard,
  Indicators and Resources. Standards and indicators include code and wording.
- A yearly scheme includes Week, First Term, Second Term and Third Term and
  requires an academic year. Weeks per term are configurable from 1 to 16.
  Repeated strands and indicators across consecutive weeks are valid.
- AI drafts require teacher review for teaching suitability and pacing. Yearly
  coverage and weekly allocations are planning proposals, not prescribed term
  allocations from NaCCA.
- Previously saved topic-only schemes retain their original data and remain
  readable and exportable. New schemes use the expanded formats.

## Curriculum evidence

`dashboard/data/nacca_resources.json` contains page text from the supplied
`NACCA Resource PAck-20260909T104425Z-1-001.zip`: eleven PDFs, with source
filenames, one-based PDF page numbers and SHA-256 hashes of the original PDFs.
It is public curriculum content, not tenant or learner data, and ships with
the application. Runtime retrieval is local; there are no external URLs or
document-controlled tools to execute.

The ten subject-specific common-core documents support Basic 7–9 / JHS 1–3:
Computing, Ghanaian Language, English, Science, RME, French, Mathematics,
Social Studies, Creative Arts and Design, and Career Technology. Subject-name
aliases are explicit in `dashboard/curriculum.py`. The primary teacher resource
pack is retained in the index but is not treated as a complete subject-specific
primary curriculum. Unsupported levels/subjects get an explicit curriculum
reference warning, rather than invented codes or JHS standards.

Lesson retrieval selects up to eight relevant pages by exact codes and topic
words. Schemes receive the matching class's curriculum pages. The prompt treats
both documents and teacher inputs as data. Server validation checks required
fields, week/day counts and order, supported codes, class level, standard/indicator
parent relationships and the occurrence of code-plus-wording in source text
(ignoring punctuation and PDF line wrapping). It rejects incomplete output or
invented wording attached to a real code. Teaching activities and resources remain
model-drafted and subject to teacher review. Source provenance is saved with the
generated content and shown on preview and exports.

Rebuild the index offline with the repository's pinned pypdf dependency:

```sh
python scripts/build_curriculum_index.py /path/to/resource-pack.zip
```

The importer reads PDF bytes without extracting archive paths and bounds file
count, uncompressed size and page count. Review new sources and mappings before
shipping an updated index. No web upload endpoint was added.

## Migration and release

Apply dashboard migration `0007_lessonnote_teacher_name_and_more` before starting
the updated application. It adds printable teacher names, scheme type and
academic year, and updates optional lesson curriculum fields. Existing schemes
default to TERMLY; there is no destructive rewrite of generated content or
approved lesson history. Roll out the index, migration, backend and templates
together through the normal Nyansa release process.

## Verification

The dashboard regression suite covers lesson review/versioning, access controls,
generation limits and exports. `dashboard/tests_curriculum.py` adds real-pack
retrieval, aliases, unsupported levels, invented codes/wording, repeated strands,
three-term completeness, malformed output, bounded forms, cross-school subject
rejection, private scheme access, legacy exports and vetting-state checks.

Local sample exports exercise the lesson PDF and lesson/termly/yearly Word
layouts. These are test fixtures, not teacher-approved teaching plans. No live
AI-provider call or production deployment is part of this local verification.

Verification on 2026-09-09: 58 dashboard tests passed on Django 6.0.8 with a
test-only fast password hasher; migration consistency and whitespace checks
passed. Rendered lesson PDF and all three Word layouts were visually inspected.
The packaged LibreOffice renderer was unavailable on this Windows machine, so
installed Microsoft Word rendered the Word QA files, followed by Windows PDF
page rasterization. Production deployment and migration application remain a
separate release step.
