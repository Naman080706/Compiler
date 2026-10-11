#include <stdio.h>

int total(int n, ...) {
    return n;
}

int main(void) {
    int a = total(1);
    int b = total(2, 3);
    int c = total(3, 4, 5);
    printf("%d %d %d\n", a, b, c);
    return 0;
}
