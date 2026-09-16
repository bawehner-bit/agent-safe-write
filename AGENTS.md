# Agent instructions

When changing this repository:

- preserve the rule: no `SUCCEEDED` result without read-back verification;
- preserve explicit `committed` semantics for errors after the commit point;
- keep the final replacement fingerprint check immediately before `os.replace`;
- do not describe replacement as atomic compare-and-swap; the final-recheck-to-rename window is a documented limitation;
- preserve atomic create-if-absent behavior for missing targets on POSIX;
- add or update tests for every safety-relevant behavior;
- do not add network or LLM dependencies to the core write path;
- distinguish observed facts from claims in documentation;
- run `python -m pytest` before claiming completion.
