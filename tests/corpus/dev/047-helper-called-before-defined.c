#include <stdio.h>

int main(void) {
    int i;
    int total = 0;
    for (i = 1; i <= 4; i++) {
        total += cube(i);
    }
    printf("cube of 2 is %d\n", cube(2));
    printf("cube of 3 is %d\n", cube(3));
    printf("sum of cubes = %d, cube of 5 = %d\n", total, cube(5));
    return 0;
}

int cube(int x) {
    return x * x * x;
}
