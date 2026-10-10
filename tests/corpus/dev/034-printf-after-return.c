#include <stdio.h>

void print_cube(int x) {
    printf("cube of %d is %d\n", x, x * x * x);
    return;
    printf("finished printing\n");
}

int main(void) {
    int i;
    for (i = 1; i <= 3; i++) {
        print_cube(i);
    }
    return 0;
}
