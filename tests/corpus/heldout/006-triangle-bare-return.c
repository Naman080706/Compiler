#include <stdio.h>

int classify(int a, int b, int c) {
    if (a + b <= c || a + c <= b || b + c <= a) {
        return;
    }
    if (a == b && b == c) {
        return 3;
    }
    if (a == b || b == c || a == c) {
        return 2;
    }
    return 1;
}

int main(void) {
    printf("3 4 5 -> %d\n", classify(3, 4, 5));
    printf("2 2 2 -> %d\n", classify(2, 2, 2));
    printf("5 5 8 -> %d\n", classify(5, 5, 8));
    return 0;
}
