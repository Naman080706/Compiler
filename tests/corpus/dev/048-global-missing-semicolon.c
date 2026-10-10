#include <stdio.h>

int limit = 10
int main(void) {
    int i;
    int count = 0;
    for (i = 1; i <= limit; i++) {
        if (i % 2 == 0) {
            count++;
        }
    }
    printf("%d even numbers up to %d\n", count, limit);
    return 0;
}
