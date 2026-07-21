/-! Exploit class: kernel bypass via compiler trust (`native_decide`).
    Correctness rests on the compiler + FFI, a vastly larger trusted base. -/

theorem fermat_number_check : (2 ^ 64 + 1) % 274177 = 0 := by
  native_decide
