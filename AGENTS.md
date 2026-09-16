# Agent instructions

When changing this repository:

- preserve the rule: no `SUCCEEDED` result without read-back verification;
- keep the final target fingerprint check immediately before `os.replace`;
- add or update tests for every safety-relevant behavior;
- do not add network or LLM dependencies to the core write path;
- distinguish observed facts from claims in documentation;
- run `python -m pytest` before claiming completion.
