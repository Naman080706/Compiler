#include <stdio.h>

int main(void) {
    int n = 10;
    int sum = 0;
    int i;
    for (i = 1; i <= n; i++) {
        sum += i;
    }
    printf("Average value: %d\n", sum / n);
    printf("Total: %d\n, sum);
    return 0;
}
