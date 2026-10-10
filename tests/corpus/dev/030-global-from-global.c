#include <stdio.h>

int limit = 10;
int half = limit / 2;

int main(void) {
    int i;
    for (i = 1; i <= limit; i++) {
        if (i == half) {
            printf("halfway at %d\n", i);
        }
    }
    return 0;
}
