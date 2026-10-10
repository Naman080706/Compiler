#include <stdio.h>

int main(void) {
    int count = 0;
    int total = 0;
    int square;
    while count < 10) {
        count++;
        square = count * count;
        total += square;
        printf("%d squared is %d\n", count, square);
        if (square > 50) {
            printf("big square\n");
        }
    }
    printf("total of squares: %d\n", total);
    return 0;
}
