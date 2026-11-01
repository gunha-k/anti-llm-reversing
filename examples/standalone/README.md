# 독립 C 프로그램

세 프로그램은 별도의 실행 파일이며, 외형 제작 도구나 main 변환을 적용하지 않았다.
각 `.o`는 일반 `main(int, char **)`을 포함한 재배치 가능한 오브젝트이다.
Linux/POSIX 환경에서 `make`로 `.c`를 `.o` 및 실행 파일로 빌드한다.
외부 라이브러리는 libc만 사용한다. 기본 빌드는 디버그 정보와 PIC를 포함한다.

## 노트

```sh
./note write memo.txt '첫 번째 노트'
./note append memo.txt '추가 메모'
./note read memo.txt
```

`write`는 기존 파일을 덮어쓰며 `append`는 끝에 한 줄을 추가한다.
텍스트 인자는 공백으로 연결되어 마지막에 개행이 붙는다.

## 간소화된 셸

```sh
./minish
./minish -c 'printf "%s\n" "hello world" > message.txt'
./minish -c 'cat < message.txt'
```

`cd`, `pwd`, `exit [0..255]`, PATH 기반 외부 명령 실행, 따옴표,
백슬래시 이스케이프, 외부 명령의 `<`, `>`, `>>`를 지원한다.
한 줄당 하나의 명령이며 최대 256개 토큰을 처리한다.
변수 확장, 글로빙, 파이프, 세미콜론, 작업 제어, 내장 명령의 리다이렉션은
지원하지 않는다. 단일/이중 따옴표는 단순 인용이며 POSIX 셸 전체 문법은 아니다.
외부 명령은 일반적인 `fork`/`execvp`로 실행한다.

## RLE 압축

```sh
./rle compress memo.txt memo.rle
./rle decompress memo.rle restored.txt
cmp memo.txt restored.txt
```

독자 형식: ASCII `RLE1` 헤더 뒤에 `(반복 횟수 1..255, 바이트 값)` 쌍을 저장한다.
빈 파일과 임의의 바이너리 데이터를 지원한다. 반복이 적으면 크기가 증가한다.
출력 파일이 이미 존재하면 실패하며 잘못된 입력이나 I/O 오류 시 생성 중인
출력 파일을 제거한다. 체크섬이 없으므로 모든 데이터 손상을 검출하지는 않는다.
