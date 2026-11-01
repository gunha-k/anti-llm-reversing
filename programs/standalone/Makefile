CC = gcc
CFLAGS = -std=c11 -O0 -g3 -Wall -Wextra -Werror -fPIC
PROGRAMS = note minish rle

.PHONY: all clean
all: $(PROGRAMS) $(PROGRAMS:=.o)

%: %.o
	$(CC) $(LDFLAGS) -o $@ $< $(LDLIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(PROGRAMS) $(PROGRAMS:=.o)
