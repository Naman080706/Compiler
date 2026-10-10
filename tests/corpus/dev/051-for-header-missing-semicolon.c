#include <stdio.h>

int main(void) {
    int n = 6;
    int total = 0;
    for (int i = 0 i < n; i++) {
        total += i * 2;
        printf("i=%d total=%d\n", i, total);
    }
    printf("total = %d over %d steps\n", total, n);
    return 0;
}
