#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int main(void) {
    int (*op)(int, int) = add;
    int first = op(2, 3);
    int second = op(10, 20);
    int third = op(first, second);
    printf("results: %d, %d and %d\n", first, second, op(third, 1));
    return 0;
}
