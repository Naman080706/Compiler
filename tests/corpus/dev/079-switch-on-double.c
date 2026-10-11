#include <stdio.h>

int main(void) {
    double grade = 3.5;
    switch (grade) {
        case 3:
            printf("three\n");
            break;
        default:
            printf("other\n");
    }
    return 0;
}
