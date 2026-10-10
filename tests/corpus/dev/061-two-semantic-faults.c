#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

void report(int value) {
    printf("value = %d\n", value);
    return value;
}

int main(void) {
    int x = 3;
    int y = add(x);
    report(y);
    return 0;
}
