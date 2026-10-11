#include <stdio.h>

typedef int (*binop)(int, int);

int mul(int a, int b) {
    return a * b;
}

int main(void) {
    binop f = mul;
    printf("product = %d\n", f(6, 7));
    return 0;
}
