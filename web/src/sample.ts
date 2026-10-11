// The program the editor starts with: one missing ';', one undeclared loop
// counter used five times (one F2 cluster) and one unused variable (a warning).
export const SAMPLE_SOURCE = `#include <stdio.h>

int main(void) {
    int total = 0;
    int unused = 3;
    for (i = 0; i < 3; i = i + 1) {
        total = total + i;
    }
    printf("%d\\n", total)
    return 0;
}
`;
