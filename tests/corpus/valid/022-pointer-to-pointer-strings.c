#include <stdio.h>

int length(const char *s) {
    int n = 0;
    while (s[n] != '\0') {
        n++;
    }
    return n;
}

int main(void) {
    const char *words[] = {"alpha", "be", "gamma"};
    char **cursor;
    char buffer[8];
    char *end = buffer + 7;
    int i;
    int total = 0;
    for (i = 0; i < 3; i++) {
        total += length(words[i]);
    }
    buffer[0] = 'x';
    buffer[1] = '\0';
    cursor = NULL;
    printf("%d %d %d\n", total, (int)(end - buffer), cursor == NULL);
    return 0;
}
