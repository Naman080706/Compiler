#include <stdio.h>

int main(void) {
    int limit = 10x;
    int count = 0;
    int n;
    for (n = 1; n <= limit * 10; n++) {
        if (n % 7 == 0) {
            count++;
        }
    }
    printf("%d multiples of 7 up to %d\n", count, limit * 10);
    return 0;
}
