#include <stdio.h>

int main(void) {
    int marks[5];
    double avg = 2.0;
    int i;
    for (i = 0; i < 5; i++) {
        marks[i] = i * 10 + 5;
    }
    printf("middle mark = %d\n", marks[avg]);
    return 0;
}
