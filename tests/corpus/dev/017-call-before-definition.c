#include <stdio.h>

int main(void) {
    int i;
    int sum = 0;
    for (i = 1; i <= 5; i++) {
        sum += square(i);
    }
    printf("sum of squares = %d\n", sum);
    return 0;
}

int square(int n) {
    return n * n;
}
