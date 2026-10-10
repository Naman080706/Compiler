#include <stdio.h>

int main(void) {
    int i = 1;
    int terms = 10;
    int sum = 0;
    while (i <= terms) {
        sum += i * i;
        i + 1 = i;
    }
    printf("loop ended with i = %d\n", i);
    printf("sum of the first %d squares = %d\n", terms, sum);
    printf("formula gives %d\n", terms * (terms + 1) * (2 * terms + 1) / 6);
    return 0;
}
