#include <stdio.h>

int main(void) {
    int c;
    int hot = 0;
    for (c = 0; c <= 40; c += 10) {
        int f = c * 9 / 5 + 32;
        printf("%d C = %d F\n", c, f);
        if c > 30) {
            hot++;
            printf("  that is hot\n");
        }
    }
    printf("%d hot readings\n", hot);
    return 0;
}
