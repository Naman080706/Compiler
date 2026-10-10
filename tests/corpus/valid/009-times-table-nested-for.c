#include <stdio.h>

int main(void) {
    int size = 5;
    int checksum = 0;
    for (int row = 1; row <= size; row++) {
        for (int col = 1; col <= size; col++) {
            printf("%d\t", row * col);
            checksum += row * col;
        }
        printf("\n");
    }
    printf("checksum = %d\n", checksum);
    return 0;
}
