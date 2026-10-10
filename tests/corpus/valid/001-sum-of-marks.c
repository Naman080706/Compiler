#include <stdio.h>

int main(void) {
    int marks[5];
    int total = 0;
    int i;
    marks[0] = 68;
    marks[1] = 74;
    marks[2] = 91;
    marks[3] = 55;
    marks[4] = 82;
    for (i = 0; i < 5; i++) {
        total += marks[i];
    }
    printf("Total marks: %d\n", total);
    printf("Average: %d\n", total / 5);
    return 0;
}
