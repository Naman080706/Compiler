#include <stdio.h>

int main(void) {
    int marks[4];
    int total = 0;
    int i;
    marks[0] = 72;
    marks[1] = 85;
    marks[2] = 64;
    marks[3] = 91;
    for (i = 0; i < 4; i++) {
        total += marks[i];@
    }
    printf("Total marks: %d\n", total);
    return 0;
}
