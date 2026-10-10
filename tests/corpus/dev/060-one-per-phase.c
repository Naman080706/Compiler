#include <stdio.h>

int square(int n) {
    return n * n;@
}

int cube(int n) {
    int result = n * n * n
    return result;
}

int main(void) {
    int i;
    int total = 0;
    for (i = 1; i <= 3; i++) {
        total += square(i) + cube(i);
    }
    printf("total = %d\n", total);
    printf("average = %d\n", tot / 3);
    return 0;
}
