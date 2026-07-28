# docs/

이 디렉터리에는 성격이 다른 두 종류가 섞여 있습니다.

- **`docs/` 바로 아래 문서는 패키지를 설명합니다.** 무엇을 보내고, 서버가 무엇으로
  답하며, 어디까지가 실서버로 확인된 것인지를 다룹니다.
- **`docs/internal/` 은 개발 기록입니다.** 감사 결과, 폐기된 계획, 설계 명세가
  들어 있습니다. 패키지를 쓰는 데 읽어야 하는 것은 아닙니다.

문서 사이트의 원본은 `index.md`·`quickstart.md`·`safety.md`·`errors.md`·
`changelog.md`·`reference/` 이며, 최상위 `mkdocs.yml` 이 이것만 사이트로 올립니다.
산문은 README 와 CHANGELOG 의 절을 그대로 끌어다 쓰고(`include-markdown`),
`reference/` 는 모듈마다 한 줄씩 mkdocstrings 지시자만 두어 docstring 에서
생성합니다. 사이트를 보려면 `pip install -e ".[docs]"` 뒤에 `mkdocs serve` 하면
됩니다.

개별 문서가 무엇을 담고 있는지는 최상위 README 의
[**문서**](../README.md#문서) 표를 보면 됩니다. 손으로 유지하는 사본이 둘이면
하나는 반드시 어긋나므로 같은 목록을 여기에 두지 않습니다.
