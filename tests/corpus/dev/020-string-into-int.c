#include <stdio.h>

int main(void) {
    int count = "five";
    int i;
    int total = 0;
    for (i = 0; i < count; i++) {
        total += 2;
    }
    printf("total = %d\n", total);
    return 0;
}
